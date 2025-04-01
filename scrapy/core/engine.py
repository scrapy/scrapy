"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spider.

For more information see docs/topics/architecture.rst

"""

from __future__ import annotations

import logging
from time import time
from traceback import format_exc
from typing import TYPE_CHECKING, Any, TypeVar, cast

from twisted.internet.defer import Deferred, succeed
from twisted.python.failure import Failure

from scrapy import signals
from scrapy.core.scheduler import BaseScheduler
from scrapy.core.scraper import Scraper, _HandleOutputDeferred
from scrapy.exceptions import CloseSpider, DontCloseSpider, IgnoreRequest
from scrapy.http import Request, Response
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    maybe_deferred_to_future,
)
from scrapy.utils.log import failure_to_exc_info, logformatter_adapter
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import global_object_name
from scrapy.utils.reactor import CallLaterOnce

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from scrapy.core.downloader import Downloader
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
    ) -> None:
        self.closing: Deferred[None] | None = None
        self.inprogress: set[Request] = set()
        self.close_if_idle: bool = close_if_idle
        self.nextcall: CallLaterOnce[None] = nextcall

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
            self.closing.callback(None)


class ExecutionEngine:
    """The engine handles some core :ref:`components <topics-components>`.

    You can access the running engine at :attr:`Crawler.engine
    <scrapy.crawler.Crawler.engine>`.
    """

    _MIN_BACK_IN_SECONDS = 0.001
    _MAX_BACK_IN_SECONDS = 5.0

    def __init__(
        self,
        crawler: Crawler,
        spider_closed_callback: Callable[[Spider], Deferred[None] | None],
    ) -> None:
        #: :ref:`Scheduler <topics-scheduler>` in use.
        self.scheduler: BaseScheduler | None = None

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
        downloader_cls: type[Downloader] = load_object(self.settings["DOWNLOADER"])
        self._back_in_seconds = self._MIN_BACK_IN_SECONDS
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
        self.running = True
        self._closewait: Deferred[None] = Deferred()
        if _start_request_processing:
            self._start_request_processing()
        await maybe_deferred_to_future(self._closewait)

    def stop(self) -> Deferred[None]:
        """Gracefully stop the execution engine"""

        @deferred_f_from_coro_f
        async def _finish_stopping_engine(_: Any) -> None:
            await maybe_deferred_to_future(
                self.signals.send_catch_log_deferred(signal=signals.engine_stopped)
            )
            self._closewait.callback(None)

        if not self.running:
            raise RuntimeError("Engine not running")

        self.running = False
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
        self.downloader.close()
        return succeed(None)

    def pause(self) -> None:
        self.paused = True

    def unpause(self) -> None:
        self.paused = False

    async def _process_start_next(self) -> None:
        """Processes the next item or request from Spider.start().

        If a request, it is scheduled. If an item, it is sent to item
        pipelines.
        """
        assert self._start is not None
        try:
            item_or_request = await self._start.__anext__()
        except StopAsyncIteration:
            self._start = None
        except CloseSpider as exception:
            if self.spider:
                await maybe_deferred_to_future(
                    self.close_spider(self.spider, reason=exception.reason)
                )
            return
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
                assert self._slot is not None  # typing
                self._slot.nextcall.schedule()

    def _scheduler_has_pending_requests(self) -> bool:
        assert self.scheduler is not None  # typing
        try:
            return self.scheduler.has_pending_requests()
        except Exception as exception:
            exception_traceback = format_exc()
            logger.error(
                f"{global_object_name(self.scheduler.has_pending_requests)} raised an exception: {exception}.\n{exception_traceback}",
                exc_info=True,
            )
            return False

    async def _wait_until_next_loop_iteration(self) -> None:
        from twisted.internet import reactor

        deferred: Deferred[None] = Deferred()
        reactor.callLater(0, deferred.callback, None)
        await maybe_deferred_to_future(deferred)

    @deferred_f_from_coro_f
    async def _start_request_processing(self) -> None:
        """Starts consuming Spider.start() output and sending scheduled
        requests."""
        # Starts the processing of scheduled requests, as well as a periodic
        # call to that processing method for scenarios where the scheduler
        # reports having pending requests but returns none.
        assert self._slot is not None  # typing
        self._slot.nextcall.schedule()

        while self._start and self.spider:
            await self._process_start_next()
            if not self.needs_backout():
                # Give room for the outcome of self._start_scheduled_requests()
                # to be processed before continuing with the next iteration.
                self._slot.nextcall.schedule()
                await self._wait_until_next_loop_iteration()

    def _start_scheduled_requests(self) -> None:
        if self._slot is None or self._slot.closing is not None or self.paused:
            return

        while not self.needs_backout():
            if self._start_scheduled_request() is None:
                break

        if self.spider_is_idle() and self._slot.close_if_idle:
            self._spider_idle()
        elif self.needs_backout():
            self._back_in_seconds = self._MIN_BACK_IN_SECONDS
        elif self._scheduler_has_pending_requests():
            # If the scheduler reports having pending requests but did not
            # actually return one, use exponential backoff to schedule a new
            # call to this method, to see if the scheduler finally returns a
            # pending request or stops reporting that it has some.
            self._slot.nextcall.schedule(self._back_in_seconds)
            # During tests, the following always evaluates to True.
            if self._back_in_seconds != self._MAX_BACK_IN_SECONDS:  # pragma: no cover
                self._back_in_seconds = min(
                    self._back_in_seconds**2, self._MAX_BACK_IN_SECONDS
                )

    def needs_backout(self) -> bool:
        """Returns ``True`` if no more requests can be sent at the moment, or
        ``False`` otherwise.

        Can be used, for example, for :ref:`lazy start request scheduling
        <start-requests-lazy>`.
        """
        assert self._slot is not None  # typing
        assert self.scraper.slot is not None  # typing
        return (
            not self.running
            or bool(self._slot.closing)
            or self.downloader.needs_backout()
            or self.scraper.slot.needs_backout()
        )

    def _start_scheduled_request(self) -> Deferred[None] | None:
        assert self._slot is not None  # typing
        assert self.spider is not None  # typing
        assert self.scheduler is not None  # typing

        try:
            request = self.scheduler.next_request()
        except Exception as exception:
            exception_traceback = format_exc()
            logger.exception(
                f"{global_object_name(self.scheduler.next_request)} raised an exception: {exception}\n{exception_traceback}"
            )
            return None
        if request is None:
            self.signals.send_catch_log(signals.scheduler_empty)
            return None

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
        return d2

    def _handle_downloader_output(
        self, result: Request | Response | Failure, request: Request
    ) -> _HandleOutputDeferred | None:
        assert self.spider is not None  # typing

        if not isinstance(result, (Request, Response, Failure)):
            raise TypeError(
                f"Incorrect type: expected Request, Response or Failure, got {type(result)}: {result!r}"
            )

        # downloader middleware can return requests (for example, redirects)
        if isinstance(result, Request):
            self.crawl(result)
            return None

        d = self.scraper.enqueue_scrape(result, request, self.spider)
        d.addErrback(
            lambda f: logger.error(
                "Error while enqueuing downloader output",
                exc_info=failure_to_exc_info(f),
                extra={"spider": self.spider},
            )
        )
        return d

    def spider_is_idle(self) -> bool:
        if self._slot is None:
            raise RuntimeError("Engine slot not assigned")
        if not self.scraper.slot.is_idle():  # type: ignore[union-attr]
            return False
        if self.downloader.active:  # downloader has pending requests
            return False
        if self._scheduler_has_pending_requests():
            return False
        if self._start is not None:  # not all start requests are handled
            self.signals.send_catch_log(signals.spider_start_blocking)
            return False
        return True

    def crawl(self, request: Request) -> None:
        """Inject the request into the spider <-> downloader pipeline"""
        if self.spider is None:
            raise RuntimeError(f"No open spider to crawl: {request}")
        self._schedule_request(request, self.spider)
        self._slot.nextcall.schedule()  # type: ignore[union-attr]

    def _schedule_request(self, request: Request, spider: Spider) -> None:
        assert self.scheduler is not None  # typing
        request_scheduled_result = self.signals.send_catch_log(
            signals.request_scheduled,
            request=request,
            spider=spider,
            dont_log=IgnoreRequest,
        )
        for handler, result in request_scheduled_result:
            if isinstance(result, Failure) and isinstance(result.value, IgnoreRequest):
                return
        try:
            request_was_enqueued = self.scheduler.enqueue_request(request)
        except Exception as exception:
            exception_traceback = format_exc()
            logger.error(
                f"{global_object_name(self.scheduler.enqueue_request)} raised an exception: {exception}\n{exception_traceback}"
            )
            request_was_enqueued = False
        if not request_was_enqueued:
            self.signals.send_catch_log(
                signals.request_dropped, request=request, spider=spider
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
        self.scheduler = build_from_crawler(self.scheduler_cls, self.crawler)
        self._slot = _Slot(close_if_idle, nextcall)
        self._start = await maybe_deferred_to_future(
            self.scraper.spidermw.process_start(spider)
        )
        if hasattr(self.scheduler, "open") and (d := self.scheduler.open(spider)):
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

        dfd.addBoth(lambda _: self.scraper.close_spider(spider))
        dfd.addErrback(log_failure("Scraper close failure"))

        if hasattr(self.scheduler, "close"):
            dfd.addBoth(lambda _: cast(BaseScheduler, self.scheduler).close(reason))
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

        dfd.addBoth(lambda _: setattr(self, "slot", None))
        dfd.addErrback(log_failure("Error while unassigning slot"))

        dfd.addBoth(lambda _: setattr(self, "spider", None))
        dfd.addErrback(log_failure("Error while unassigning spider"))

        dfd.addBoth(lambda _: self._spider_closed_callback(spider))

        return dfd
