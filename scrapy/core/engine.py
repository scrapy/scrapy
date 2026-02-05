"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spider.

For more information see docs/topics/architecture.rst

"""

from __future__ import annotations

import asyncio
import logging
import warnings
from time import time
from traceback import format_exc
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import CancelledError, Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import signals
from scrapy.core.scheduler import BaseScheduler
from scrapy.core.scraper import Scraper
from scrapy.exceptions import (
    CloseSpider,
    DontCloseSpider,
    IgnoreRequest,
    ScrapyDeprecationWarning,
)
from scrapy.http import Request, Response
from scrapy.utils.asyncio import (
    AsyncioLoopingCall,
    create_looping_call,
    is_asyncio_available,
)
from scrapy.utils.defer import (
    _schedule_coro,
    deferred_from_coro,
    ensure_awaitable,
    maybe_deferred_to_future,
)
from scrapy.utils.deprecate import argument_is_required
from scrapy.utils.log import failure_to_exc_info, logformatter_adapter
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import global_object_name
from scrapy.utils.reactor import CallLaterOnce

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine, Generator

    from twisted.internet.task import LoopingCall

    from scrapy.core.downloader import Downloader
    from scrapy.crawler import Crawler
    from scrapy.logformatter import LogFormatter
    from scrapy.settings import BaseSettings, Settings
    from scrapy.signalmanager import SignalManager
    from scrapy.spiders import Spider


logger = logging.getLogger(__name__)


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
        self.heartbeat: AsyncioLoopingCall | LoopingCall = create_looping_call(
            nextcall.schedule
        )

    def add_request(self, request: Request) -> None:
        self.inprogress.add(request)

    def remove_request(self, request: Request) -> None:
        self.inprogress.remove(request)
        self._maybe_fire_closing()

    async def close(self) -> None:
        self.closing = Deferred()
        self._maybe_fire_closing()
        await maybe_deferred_to_future(self.closing)

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
        spider_closed_callback: Callable[
            [Spider], Coroutine[Any, Any, None] | Deferred[None] | None
        ],
    ) -> None:
        self.crawler: Crawler = crawler
        self.settings: Settings = crawler.settings
        self.signals: SignalManager = crawler.signals
        assert crawler.logformatter
        self.logformatter: LogFormatter = crawler.logformatter
        self._slot: _Slot | None = None
        self.spider: Spider | None = None
        self.running: bool = False
        self._starting: bool = False
        self._stopping: bool = False
        self.paused: bool = False
        self._spider_closed_callback: Callable[
            [Spider], Coroutine[Any, Any, None] | Deferred[None] | None
        ] = spider_closed_callback
        self.start_time: float | None = None
        self._start: AsyncIterator[Any] | None = None
        self._closewait: Deferred[None] | None = None
        self._start_request_processing_awaitable: (
            asyncio.Future[None] | Deferred[None] | None
        ) = None
        downloader_cls: type[Downloader] = load_object(self.settings["DOWNLOADER"])
        try:
            self.scheduler_cls: type[BaseScheduler] = self._get_scheduler_class(
                crawler.settings
            )
            self.downloader: Downloader = downloader_cls(crawler)
            self._downloader_fetch_needs_spider: bool = argument_is_required(
                self.downloader.fetch, "spider"
            )
            if self._downloader_fetch_needs_spider:
                warnings.warn(
                    f"The fetch() method of {global_object_name(downloader_cls)} requires a spider argument,"
                    f" this is deprecated and the argument will not be passed in future Scrapy versions.",
                    ScrapyDeprecationWarning,
                    stacklevel=2,
                )

            self.scraper: Scraper = Scraper(crawler)
        except Exception:
            if hasattr(self, "downloader"):
                self.downloader.close()
            raise

    def _get_scheduler_class(self, settings: BaseSettings) -> type[BaseScheduler]:
        scheduler_cls: type[BaseScheduler] = load_object(settings["SCHEDULER"])
        if not issubclass(scheduler_cls, BaseScheduler):
            raise TypeError(
                f"The provided scheduler class ({settings['SCHEDULER']})"
                " does not fully implement the scheduler interface"
            )
        return scheduler_cls

    def start(self, _start_request_processing=True) -> Deferred[None]:
        warnings.warn(
            "ExecutionEngine.start() is deprecated, use start_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(
            self.start_async(_start_request_processing=_start_request_processing)
        )

    async def start_async(self, *, _start_request_processing: bool = True) -> None:
        """Start the execution engine.

        .. versionadded:: 2.14
        """
        if self._starting:
            raise RuntimeError("Engine already running")
        self.start_time = time()
        self._starting = True
        await self.signals.send_catch_log_async(signal=signals.engine_started)
        if self._stopping:
            # band-aid until https://github.com/scrapy/scrapy/issues/6916
            return
        if _start_request_processing and self.spider is None:
            # require an opened spider when not run in scrapy shell
            return
        self.running = True
        self._closewait = Deferred()
        if _start_request_processing:
            coro = self._start_request_processing()
            if is_asyncio_available():
                # not wrapping in a Deferred here to avoid https://github.com/twisted/twisted/issues/12470
                # (can happen when this is cancelled, e.g. in test_close_during_start_iteration())
                self._start_request_processing_awaitable = asyncio.ensure_future(coro)
            else:
                self._start_request_processing_awaitable = Deferred.fromCoroutine(coro)
        await maybe_deferred_to_future(self._closewait)

    def stop(self) -> Deferred[None]:
        warnings.warn(
            "ExecutionEngine.stop() is deprecated, use stop_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.stop_async())

    async def stop_async(self) -> None:
        """Gracefully stop the execution engine.

        .. versionadded:: 2.14
        """

        if not self._starting:
            raise RuntimeError("Engine not running")

        self.running = self._starting = False
        self._stopping = True
        if self._start_request_processing_awaitable is not None:
            if (
                not is_asyncio_available()
                or self._start_request_processing_awaitable
                is not asyncio.current_task()
            ):
                # If using the asyncio loop and stop_async() was called from
                # start() itself, we can't cancel it, and _start_request_processing()
                # will exit via the self.running check.
                self._start_request_processing_awaitable.cancel()
            self._start_request_processing_awaitable = None
        if self.spider is not None:
            await self.close_spider_async(reason="shutdown")
        await self.signals.send_catch_log_async(signal=signals.engine_stopped)
        if self._closewait:
            self._closewait.callback(None)

    def close(self) -> Deferred[None]:
        warnings.warn(
            "ExecutionEngine.close() is deprecated, use close_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.close_async())

    async def close_async(self) -> None:
        """
        Gracefully close the execution engine.
        If it has already been started, stop it. In all cases, close the spider and the downloader.
        """
        if self.running:
            await self.stop_async()  # will also close spider and downloader
        elif self.spider is not None:
            await self.close_spider_async(
                reason="shutdown"
            )  # will also close downloader
        elif hasattr(self, "downloader"):
            self.downloader.close()

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
                _schedule_coro(
                    self.scraper.start_itemproc_async(item_or_request, response=None)
                )
                self._slot.nextcall.schedule()

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

            while self._start and self.spider and self.running:
                await self._process_start_next()
                if not self.needs_backout():
                    # Give room for the outcome of self._process_start_next() to be
                    # processed before continuing with the next iteration.
                    self._slot.nextcall.schedule()
                    await self._slot.nextcall.wait()
        except (asyncio.exceptions.CancelledError, CancelledError):
            # self.stop_async() has cancelled us, nothing to do
            return
        except Exception:
            # an error happened, log it and stop the engine
            self._start_request_processing_awaitable = None
            logger.error(
                "Error while processing requests from start()",
                exc_info=True,
                extra={"spider": self.spider},
            )
            await self.stop_async()

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
        warnings.warn(
            "ExecutionEngine.download() is deprecated, use download_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.download_async(request))

    async def download_async(self, request: Request) -> Response:
        """Return a coroutine which fires with a Response as result.

         Only downloader middlewares are applied.

        .. versionadded:: 2.14
        """
        if self.spider is None:
            raise RuntimeError(f"No open spider to crawl: {request}")
        try:
            response_or_request = await maybe_deferred_to_future(
                self._download(request)
            )
        finally:
            assert self._slot is not None
            self._slot.remove_request(request)
        if isinstance(response_or_request, Request):
            return await self.download_async(response_or_request)
        return response_or_request

    @inlineCallbacks
    def _download(
        self, request: Request
    ) -> Generator[Deferred[Any], Any, Response | Request]:
        assert self._slot is not None  # typing
        assert self.spider is not None

        self._slot.add_request(request)
        try:
            result: Response | Request
            if self._downloader_fetch_needs_spider:
                result = yield self.downloader.fetch(request, self.spider)
            else:
                result = yield self.downloader.fetch(request)
            if not isinstance(result, (Response, Request)):
                raise TypeError(
                    f"Incorrect type: expected Response or Request, got {type(result)}: {result!r}"
                )
            if isinstance(result, Response):
                if result.request is None:
                    result.request = request
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
        finally:
            self._slot.nextcall.schedule()

    def open_spider(self, spider: Spider, close_if_idle: bool = True) -> Deferred[None]:
        warnings.warn(
            "ExecutionEngine.open_spider() is deprecated, use open_spider_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.open_spider_async(close_if_idle=close_if_idle))

    async def open_spider_async(self, *, close_if_idle: bool = True) -> None:
        assert self.crawler.spider
        if self._slot is not None:
            raise RuntimeError(
                f"No free spider slot when opening {self.crawler.spider.name!r}"
            )
        logger.info("Spider opened", extra={"spider": self.crawler.spider})
        self.spider = self.crawler.spider
        nextcall = CallLaterOnce(self._start_scheduled_requests)
        scheduler = build_from_crawler(self.scheduler_cls, self.crawler)
        self._slot = _Slot(close_if_idle, nextcall, scheduler)
        self._start = await self.scraper.spidermw.process_start()
        if hasattr(scheduler, "open") and (d := scheduler.open(self.crawler.spider)):
            await maybe_deferred_to_future(d)
        await self.scraper.open_spider_async()
        assert self.crawler.stats
        if argument_is_required(self.crawler.stats.open_spider, "spider"):
            warnings.warn(
                f"The open_spider() method of {global_object_name(type(self.crawler.stats))} requires a spider argument,"
                f" this is deprecated and the argument will not be passed in future Scrapy versions.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
            self.crawler.stats.open_spider(spider=self.crawler.spider)
        else:
            self.crawler.stats.open_spider()
        await self.signals.send_catch_log_async(
            signals.spider_opened, spider=self.crawler.spider
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
            _schedule_coro(self.close_spider_async(reason=ex.reason))

    def close_spider(self, spider: Spider, reason: str = "cancelled") -> Deferred[None]:
        warnings.warn(
            "ExecutionEngine.close_spider() is deprecated, use close_spider_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.close_spider_async(reason=reason))

    async def close_spider_async(self, *, reason: str = "cancelled") -> None:
        """Close (cancel) spider and clear all its outstanding requests.

        .. versionadded:: 2.14
        """
        if self.spider is None:
            raise RuntimeError("Spider not opened")

        if self._slot is None:
            raise RuntimeError("Engine slot not assigned")

        if self._slot.closing is not None:
            await maybe_deferred_to_future(self._slot.closing)
            return

        spider = self.spider

        logger.info(
            "Closing spider (%(reason)s)", {"reason": reason}, extra={"spider": spider}
        )

        def log_failure(msg: str) -> None:
            logger.error(msg, exc_info=True, extra={"spider": spider})  # noqa: LOG014

        try:
            await self._slot.close()
        except Exception:
            log_failure("Slot close failure")

        try:
            self.downloader.close()
        except Exception:
            log_failure("Downloader close failure")

        try:
            await self.scraper.close_spider_async()
        except Exception:
            log_failure("Scraper close failure")

        if hasattr(self._slot.scheduler, "close"):
            try:
                if (d := self._slot.scheduler.close(reason)) is not None:
                    await maybe_deferred_to_future(d)
            except Exception:
                log_failure("Scheduler close failure")

        try:
            await self.signals.send_catch_log_async(
                signal=signals.spider_closed,
                spider=spider,
                reason=reason,
            )
        except Exception:
            log_failure("Error while sending spider_close signal")

        assert self.crawler.stats
        try:
            if argument_is_required(self.crawler.stats.close_spider, "spider"):
                warnings.warn(
                    f"The close_spider() method of {global_object_name(type(self.crawler.stats))} requires a spider argument,"
                    f" this is deprecated and the argument will not be passed in future Scrapy versions.",
                    ScrapyDeprecationWarning,
                    stacklevel=2,
                )
                self.crawler.stats.close_spider(
                    spider=self.crawler.spider, reason=reason
                )
            else:
                self.crawler.stats.close_spider(reason=reason)
        except Exception:
            log_failure("Stats close failure")

        logger.info(
            "Spider closed (%(reason)s)",
            {"reason": reason},
            extra={"spider": spider},
        )

        self._slot = None
        self.spider = None

        try:
            await ensure_awaitable(self._spider_closed_callback(spider))
        except Exception:
            log_failure("Error running spider_closed_callback")
