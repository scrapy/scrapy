"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spider.

For more information see docs/topics/architecture.rst

"""

from __future__ import annotations

import asyncio
import logging
from time import time
from traceback import format_exc
from typing import TYPE_CHECKING, Any, TypeVar, cast

from twisted.internet.defer import CancelledError, Deferred, inlineCallbacks, succeed
from twisted.internet.task import LoopingCall
from twisted.python.failure import Failure

from scrapy import signals
from scrapy.core.scraper import Scraper
from scrapy.exceptions import CloseSpider, DontCloseSpider, IgnoreRequest
from scrapy.http import Request, Response
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    maybe_deferred_to_future,
)
from scrapy.utils.log import failure_to_exc_info, logformatter_adapter
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.reactor import CallLaterOnce

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Generator

    from scrapy.core.downloader import Downloader
    from scrapy.core.scheduler import BaseScheduler
    from scrapy.crawler import Crawler
    from scrapy.logformatter import LogFormatter
    from scrapy.settings import BaseSettings, Settings
    from scrapy.signalmanager import SignalManager
    from scrapy.spiders import Spider


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class _Slot:
    def __init__(
        self,
        close_if_idle: bool,
        nextcall: CallLaterOnce[None],
        scheduler: BaseScheduler,
    ) -> None:
        self.closing: Deferred[None] | None = None
        self.inprogress: set[Request] = set()
        self.close_if_idle: bool = close_if_idle
        self.nextcall: CallLaterOnce[None] = nextcall
        self.scheduler: BaseScheduler = scheduler
        self.heartbeat: LoopingCall = LoopingCall(nextcall.schedule)

    def add_request(self, request: Request) -> None:
        self.inprogress.add(request)

    def remove_request(self, request: Request) -> None:
        self.inprogress.remove(request)
        self._maybe_fire_closing()

    def close(self) -> Deferred[None]:
        self.closing = Deferred()
        self._maybe_fire_closing()
        return self.closing

    def _maybe_fire_closing(self) -> None:
        if self.closing is not None and not self.inprogress:
            if self.nextcall:
                self.nextcall.cancel()
                if self.heartbeat.running:
                    self.heartbeat.stop()
            self.closing.callback(None)


class ExecutionEngine:
    _SLOT_HEARTBEAT_INTERVAL: float = 5.0

    def __init__(
        self,
        crawler: Crawler,
        spider_closed_callback: Callable[[Spider], Deferred[None] | None],
    ) -> None:
        self.crawler: Crawler = crawler
        self.settings: Settings = crawler.settings
        self.signals: SignalManager = crawler.signals
        assert crawler.logformatter
        self.logformatter: LogFormatter = crawler.logformatter
        self._slot: _Slot | None = None
        self.spider: Spider | None = None
        self.running: bool = False
        self.paused: bool = False
        self._spider_closed_callback: Callable[[Spider], Deferred[None] | None] = (
            spider_closed_callback
        )
        self.start_time: float | None = None
        self._start: AsyncIterator[Any] | None = None
        self._closewait: Deferred[None] | None = None
        self._start_request_processing_dfd: Deferred[None] | None = None
        downloader_cls: type[Downloader] = load_object(self.settings["DOWNLOADER"])
        try:
            self.scheduler_cls: type[BaseScheduler] = self._get_scheduler_class(
                crawler.settings
            )
            self.downloader: Downloader = downloader_cls(crawler)
            self.scraper: Scraper = Scraper(crawler)
        except Exception:
            self.close()
            raise

    def _get_scheduler_class(self, settings: BaseSettings) -> type[BaseScheduler]:
        from scrapy.core.scheduler import BaseScheduler

        scheduler_cls: type[BaseScheduler] = load_object(settings["SCHEDULER"])
        if not issubclass(scheduler_cls, BaseScheduler):
            raise TypeError(
                f"The provided scheduler class ({settings['SCHEDULER']})"
                " does not fully implement the scheduler interface"
            )
        return scheduler_cls

    @deferred_f_from_coro_f
    async def start(self, _start_request_processing=True) -> None:
        if self.running:
            raise RuntimeError("Engine already running")
        self.start_time = time()
        await maybe_deferred_to_future(
            self.signals.send_catch_log_deferred(signal=signals.engine_started)
        )
        if _start_request_processing and self.spider is None:
            # require an opened spider when not run in scrapy shell
            return
        self.running = True
        self._closewait = Deferred()
        if _start_request_processing:
            self._start_request_processing_dfd = self._start_request_processing()
        await maybe_deferred_to_future(self._closewait)

    def stop(self) -> Deferred[None]:
        """Gracefully stop the execution engine"""

        @deferred_f_from_coro_f
        async def _finish_stopping_engine(_: Any) -> None:
            await maybe_deferred_to_future(
                self.signals.send_catch_log_deferred(signal=signals.engine_stopped)
            )
            if self._closewait:
                self._closewait.callback(None)

        if not self.running:
            raise RuntimeError("Engine not running")

        self.running = False
        if self._start_request_processing_dfd is not None:
            self._start_request_processing_dfd.cancel()
            self._start_request_processing_dfd = None
        dfd = (
            self.close_spider(self.spider, reason="shutdown")
            if self.spider is not None
            else succeed(None)
        )
        return dfd.addBoth(_finish_stopping_engine)

    def close(self) -> Deferred[None]:
        """
        Gracefully close the execution engine.
        If it has already been started, stop it. In all cases, close the spider and the downloader.
        """
        if self.running:
            return self.stop()  # will also close spider and downloader
        if self.spider is not None:
            return self.close_spider(
                self.spider, reason="shutdown"
            )  # will also close downloader
        if hasattr(self, "downloader"):
            self.downloader.close()
        return succeed(None)

    def pause(self) -> None:
        self.paused = True

    def unpause(self) -> None:
        self.paused = False

    async def _process_start_next(self):
        """Processes the next item or request from Spider.start().

        If a request, it is scheduled. If an item, it is sent to item
        pipelines.
        """
        try:
            item_or_request = await self._start.__anext__()
        except StopAsyncIteration:
            self._start = None
        except Exception as exception:
            self._start = None
            exception_traceback = format_exc()
            logger.error(
                f"Error while reading start items and requests: {exception}.\n{exception_traceback}",
                exc_info=True,
            )
        else:
            if not self.spider:
                return  # spider already closed
            if isinstance(item_or_request, Request):
                self.crawl(item_or_request)
            else:
                self.scraper.start_itemproc(item_or_request, response=None)
                self._slot.nextcall.schedule()

    @deferred_f_from_coro_f
    async def _start_request_processing(self) -> None:
        """Starts consuming Spider.start() output and sending scheduled
        requests."""
        # Starts the processing of scheduled requests, as well as a periodic
        # call to that processing method for scenarios where the scheduler
        # reports having pending requests but returns none.
        try:
            assert self._slot is not None  # typing
            self._slot.nextcall.schedule()
            self._slot.heartbeat.start(self._SLOT_HEARTBEAT_INTERVAL)

            while self._start and self.spider:
                await self._process_start_next()
                if not self.needs_backout():
                    # Give room for the outcome of self._process_start_next() to be
                    # processed before continuing with the next iteration.
                    self._slot.nextcall.schedule()
                    await self._slot.nextcall.wait()
        except (asyncio.exceptions.CancelledError, CancelledError):
            # self.stop() has cancelled us, nothing to do
            return
        except Exception:
            # an error happened, log it and stop the engine
            self._start_request_processing_dfd = None
            logger.error(
                "Error while processing requests from start()",
                exc_info=True,
                extra={"spider": self.spider},
            )
            await maybe_deferred_to_future(self.stop())

    def _start_scheduled_requests(self) -> None:
        if self._slot is None or self._slot.closing is not None or self.paused:
            return

        while not self.needs_backout():
            if not self._start_scheduled_request():
                break

        if self.spider_is_idle() and self._slot.close_if_idle:
            self._spider_idle()

    def needs_backout(self) -> bool:
        """Returns ``True`` if no more requests can be sent at the moment, or
        ``False`` otherwise.

        See :ref:`start-requests-lazy` for an example.
        """
        assert self.scraper.slot is not None  # typing
        return (
            not self.running
            or not self._slot
            or bool(self._slot.closing)
            or self.downloader.needs_backout()
            or self.scraper.slot.needs_backout()
        )

    def _start_scheduled_request(self) -> bool:
        assert self._slot is not None  # typing
        assert self.spider is not None  # typing

        request = self._slot.scheduler.next_request()
        if request is None:
            self.signals.send_catch_log(signals.scheduler_empty)
            return False

        d: Deferred[Response | Request] = self._download(request)
        d.addBoth(self._handle_downloader_output, request)
        d.addErrback(
            lambda f: logger.info(
                "Error while handling downloader output",
                exc_info=failure_to_exc_info(f),
                extra={"spider": self.spider},
            )
        )

        def _remove_request(_: Any) -> None:
            assert self._slot
            self._slot.remove_request(request)

        d2: Deferred[None] = d.addBoth(_remove_request)
        d2.addErrback(
            lambda f: logger.info(
                "Error while removing request from slot",
                exc_info=failure_to_exc_info(f),
                extra={"spider": self.spider},
            )
        )
        slot = self._slot
        d2.addBoth(lambda _: slot.nextcall.schedule())
        d2.addErrback(
            lambda f: logger.info(
                "Error while scheduling new request",
                exc_info=failure_to_exc_info(f),
                extra={"spider": self.spider},
            )
        )
        return True

    @inlineCallbacks
    def _handle_downloader_output(
        self, result: Request | Response | Failure, request: Request
    ) -> Generator[Deferred[Any], Any, None]:
        if not isinstance(result, (Request, Response, Failure)):
            raise TypeError(
                f"Incorrect type: expected Request, Response or Failure, got {type(result)}: {result!r}"
            )

        # downloader middleware can return requests (for example, redirects)
        if isinstance(result, Request):
            self.crawl(result)
            return

        try:
            yield self.scraper.enqueue_scrape(result, request)
        except Exception:
            assert self.spider is not None
            logger.error(
                "Error while enqueuing scrape",
                exc_info=True,
                extra={"spider": self.spider},
            )

    def spider_is_idle(self) -> bool:
        if self._slot is None:
            raise RuntimeError("Engine slot not assigned")
        if not self.scraper.slot.is_idle():  # type: ignore[union-attr]
            return False
        if self.downloader.active:  # downloader has pending requests
            return False
        if self._start is not None:  # not all start requests are handled
            return False
        return not self._slot.scheduler.has_pending_requests()

    def crawl(self, request: Request) -> None:
        """Inject the request into the spider <-> downloader pipeline"""
        if self.spider is None:
            raise RuntimeError(f"No open spider to crawl: {request}")
        self._schedule_request(request)
        self._slot.nextcall.schedule()  # type: ignore[union-attr]

    def _schedule_request(self, request: Request) -> None:
        request_scheduled_result = self.signals.send_catch_log(
            signals.request_scheduled,
            request=request,
            spider=self.spider,
            dont_log=IgnoreRequest,
        )
        for handler, result in request_scheduled_result:
            if isinstance(result, Failure) and isinstance(result.value, IgnoreRequest):
                return
        if not self._slot.scheduler.enqueue_request(request):  # type: ignore[union-attr]
            self.signals.send_catch_log(
                signals.request_dropped, request=request, spider=self.spider
            )

    def download(self, request: Request) -> Deferred[Response]:
        """Return a Deferred which fires with a Response as result, only downloader middlewares are applied"""
        if self.spider is None:
            raise RuntimeError(f"No open spider to crawl: {request}")
        d: Deferred[Response | Request] = self._download(request)
        # Deferred.addBoth() overloads don't seem to support a Union[_T, Deferred[_T]] return type
        d2: Deferred[Response] = d.addBoth(self._downloaded, request)  # type: ignore[call-overload]
        return d2

    def _downloaded(
        self, result: Response | Request | Failure, request: Request
    ) -> Deferred[Response] | Response | Failure:
        assert self._slot is not None  # typing
        self._slot.remove_request(request)
        return self.download(result) if isinstance(result, Request) else result

    def _download(self, request: Request) -> Deferred[Response | Request]:
        assert self._slot is not None  # typing

        self._slot.add_request(request)

        def _on_success(result: Response | Request) -> Response | Request:
            if not isinstance(result, (Response, Request)):
                raise TypeError(
                    f"Incorrect type: expected Response or Request, got {type(result)}: {result!r}"
                )
            if isinstance(result, Response):
                if result.request is None:
                    result.request = request
                assert self.spider is not None
                logkws = self.logformatter.crawled(result.request, result, self.spider)
                if logkws is not None:
                    logger.log(
                        *logformatter_adapter(logkws), extra={"spider": self.spider}
                    )
                self.signals.send_catch_log(
                    signal=signals.response_received,
                    response=result,
                    request=result.request,
                    spider=self.spider,
                )
            return result

        def _on_complete(_: _T) -> _T:
            assert self._slot is not None
            self._slot.nextcall.schedule()
            return _

        assert self.spider is not None
        dwld: Deferred[Response | Request] = self.downloader.fetch(request, self.spider)
        dwld.addCallback(_on_success)
        dwld.addBoth(_on_complete)
        return dwld

    @deferred_f_from_coro_f
    async def open_spider(
        self,
        spider: Spider,
        close_if_idle: bool = True,
    ) -> None:
        if self._slot is not None:
            raise RuntimeError(f"No free spider slot when opening {spider.name!r}")
        logger.info("Spider opened", extra={"spider": spider})
        self.spider = spider
        nextcall = CallLaterOnce(self._start_scheduled_requests)
        scheduler = build_from_crawler(self.scheduler_cls, self.crawler)
        self._slot = _Slot(close_if_idle, nextcall, scheduler)
        self._start = await self.scraper.spidermw.process_start(spider)
        if hasattr(scheduler, "open") and (d := scheduler.open(spider)):
            await maybe_deferred_to_future(d)
        await maybe_deferred_to_future(self.scraper.open_spider(spider))
        assert self.crawler.stats
        self.crawler.stats.open_spider(spider)
        await maybe_deferred_to_future(
            self.signals.send_catch_log_deferred(signals.spider_opened, spider=spider)
        )

    def _spider_idle(self) -> None:
        """
        Called when a spider gets idle, i.e. when there are no remaining requests to download or schedule.
        It can be called multiple times. If a handler for the spider_idle signal raises a DontCloseSpider
        exception, the spider is not closed until the next loop and this function is guaranteed to be called
        (at least) once again. A handler can raise CloseSpider to provide a custom closing reason.
        """
        assert self.spider is not None  # typing
        expected_ex = (DontCloseSpider, CloseSpider)
        res = self.signals.send_catch_log(
            signals.spider_idle, spider=self.spider, dont_log=expected_ex
        )
        detected_ex = {
            ex: x.value
            for _, x in res
            for ex in expected_ex
            if isinstance(x, Failure) and isinstance(x.value, ex)
        }
        if DontCloseSpider in detected_ex:
            return
        if self.spider_is_idle():
            ex = detected_ex.get(CloseSpider, CloseSpider(reason="finished"))
            assert isinstance(ex, CloseSpider)  # typing
            self.close_spider(self.spider, reason=ex.reason)

    def close_spider(self, spider: Spider, reason: str = "cancelled") -> Deferred[None]:
        """Close (cancel) spider and clear all its outstanding requests"""
        if self._slot is None:
            raise RuntimeError("Engine slot not assigned")

        if self._slot.closing is not None:
            return self._slot.closing

        logger.info(
            "Closing spider (%(reason)s)", {"reason": reason}, extra={"spider": spider}
        )

        dfd = self._slot.close()

        def log_failure(msg: str) -> Callable[[Failure], None]:
            def errback(failure: Failure) -> None:
                logger.error(
                    msg, exc_info=failure_to_exc_info(failure), extra={"spider": spider}
                )

            return errback

        dfd.addBoth(lambda _: self.downloader.close())
        dfd.addErrback(log_failure("Downloader close failure"))

        dfd.addBoth(lambda _: self.scraper.close_spider())
        dfd.addErrback(log_failure("Scraper close failure"))

        if hasattr(self._slot.scheduler, "close"):
            dfd.addBoth(lambda _: cast(_Slot, self._slot).scheduler.close(reason))
            dfd.addErrback(log_failure("Scheduler close failure"))

        dfd.addBoth(
            lambda _: self.signals.send_catch_log_deferred(
                signal=signals.spider_closed,
                spider=spider,
                reason=reason,
            )
        )
        dfd.addErrback(log_failure("Error while sending spider_close signal"))

        def close_stats(_: Any) -> None:
            assert self.crawler.stats
            self.crawler.stats.close_spider(spider, reason=reason)

        dfd.addBoth(close_stats)
        dfd.addErrback(log_failure("Stats close failure"))

        dfd.addBoth(
            lambda _: logger.info(
                "Spider closed (%(reason)s)",
                {"reason": reason},
                extra={"spider": spider},
            )
        )

        def unassign_slot(_: Any) -> None:
            self._slot = None

        dfd.addBoth(unassign_slot)
        dfd.addErrback(log_failure("Error while unassigning slot"))

        def unassign_spider(_: Any) -> None:
            self.spider = None

        dfd.addBoth(unassign_spider)
        dfd.addErrback(log_failure("Error while unassigning spider"))

        dfd.addBoth(lambda _: self._spider_closed_callback(spider))
        dfd.addErrback(log_failure("Error running spider_closed_callback"))

        return dfd
