"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spider.

For more information see docs/topics/architecture.rst

"""

from __future__ import annotations

import logging
from time import time
from typing import TYPE_CHECKING, Any, TypeVar, cast

from itemadapter import is_item
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.task import LoopingCall
from twisted.python.failure import Failure

from scrapy import signals
from scrapy.core.downloader import Downloader
from scrapy.core.scraper import Scraper, _HandleOutputDeferred
from scrapy.exceptions import CloseSpider, DontCloseSpider, IgnoreRequest
from scrapy.http import Request, Response
from scrapy.logformatter import LogFormatter
from scrapy.settings import Settings
from scrapy.signalmanager import SignalManager
from scrapy.utils.log import failure_to_exc_info, logformatter_adapter
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.reactor import CallLaterOnce

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Iterator

    from scrapy.core.scheduler import BaseScheduler
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings
    from scrapy.spiders import Spider


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class Slot:
    def __init__(
        self,
        start_requests: Iterable[Request],
        close_if_idle: bool,
        nextcall: CallLaterOnce[None],
        scheduler: BaseScheduler,
    ) -> None:
        self.closing: Deferred[None] | None = None
        self.inprogress: set[Request] = set()
        self.start_requests: Iterator[Request] | None = iter(start_requests)
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
        self.slot: Slot | None = None
        self.spider: Spider | None = None
        self.running: bool = False
        self.paused: bool = False
        self.scheduler_cls: type[BaseScheduler] = self._get_scheduler_class(
            crawler.settings
        )
        downloader_cls: type[Downloader] = load_object(self.settings["DOWNLOADER"])
        self.downloader: Downloader = downloader_cls(crawler)
        self.scraper: Scraper = Scraper(crawler)
        self._spider_closed_callback: Callable[[Spider], Deferred[None] | None] = (
            spider_closed_callback
        )
        self.start_time: float | None = None

    def _get_scheduler_class(self, settings: BaseSettings) -> type[BaseScheduler]:
        from scrapy.core.scheduler import BaseScheduler

        scheduler_cls: type[BaseScheduler] = load_object(settings["SCHEDULER"])
        if not issubclass(scheduler_cls, BaseScheduler):
            raise TypeError(
                f"The provided scheduler class ({settings['SCHEDULER']})"
                " does not fully implement the scheduler interface"
            )
        return scheduler_cls

    @inlineCallbacks
    def start(self) -> Generator[Deferred[Any], Any, None]:
        if self.running:
            raise RuntimeError("Engine already running")
        self.start_time = time()
        yield self.signals.send_catch_log_deferred(signal=signals.engine_started)
        self.running = True
        self._closewait: Deferred[None] = Deferred()
        yield self._closewait

    def stop(self) -> Deferred[None]:
        """Gracefully stop the execution engine"""

        @inlineCallbacks
        def _finish_stopping_engine(_: Any) -> Generator[Deferred[Any], Any, None]:
            yield self.signals.send_catch_log_deferred(signal=signals.engine_stopped)
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

    def _next_request(self) -> None:
        if self.slot is None:
            return

        assert self.spider is not None  # typing

        if self.paused:
            return

        while (
            not self._needs_backout()
            and self._next_request_from_scheduler() is not None
        ):
            pass

        if self.slot.start_requests is not None and not self._needs_backout():
            try:
                request_or_item = next(self.slot.start_requests)
            except StopIteration:
                self.slot.start_requests = None
            except Exception:
                self.slot.start_requests = None
                logger.error(
                    "Error while obtaining start requests",
                    exc_info=True,
                    extra={"spider": self.spider},
                )
            else:
                if isinstance(request_or_item, Request):
                    self.crawl(request_or_item)
                elif is_item(request_or_item):
                    self.scraper.start_itemproc(request_or_item, response=None)
                else:
                    logger.error(
                        f"Got {request_or_item!r} among start requests. Only "
                        f"requests and items are supported. It will be "
                        f"ignored."
                    )

        if self.spider_is_idle() and self.slot.close_if_idle:
            self._spider_idle()

    def _needs_backout(self) -> bool:
        assert self.slot is not None  # typing
        assert self.scraper.slot is not None  # typing
        return (
            not self.running
            or bool(self.slot.closing)
            or self.downloader.needs_backout()
            or self.scraper.slot.needs_backout()
        )

    def _next_request_from_scheduler(self) -> Deferred[None] | None:
        assert self.slot is not None  # typing
        assert self.spider is not None  # typing

        request = self.slot.scheduler.next_request()
        if request is None:
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
            assert self.slot
            self.slot.remove_request(request)

        d2: Deferred[None] = d.addBoth(_remove_request)
        d2.addErrback(
            lambda f: logger.info(
                "Error while removing request from slot",
                exc_info=failure_to_exc_info(f),
                extra={"spider": self.spider},
            )
        )
        slot = self.slot
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
        if self.slot is None:
            raise RuntimeError("Engine slot not assigned")
        if not self.scraper.slot.is_idle():  # type: ignore[union-attr]
            return False
        if self.downloader.active:  # downloader has pending requests
            return False
        if self.slot.start_requests is not None:  # not all start requests are handled
            return False
        if self.slot.scheduler.has_pending_requests():
            return False
        return True

    def crawl(self, request: Request) -> None:
        """Inject the request into the spider <-> downloader pipeline"""
        if self.spider is None:
            raise RuntimeError(f"No open spider to crawl: {request}")
        self._schedule_request(request, self.spider)
        self.slot.nextcall.schedule()  # type: ignore[union-attr]

    def _schedule_request(self, request: Request, spider: Spider) -> None:
        request_scheduled_result = self.signals.send_catch_log(
            signals.request_scheduled,
            request=request,
            spider=spider,
            dont_log=IgnoreRequest,
        )
        for handler, result in request_scheduled_result:
            if isinstance(result, Failure) and isinstance(result.value, IgnoreRequest):
                return
        if not self.slot.scheduler.enqueue_request(request):  # type: ignore[union-attr]
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
        assert self.slot is not None  # typing
        self.slot.remove_request(request)
        return self.download(result) if isinstance(result, Request) else result

    def _download(self, request: Request) -> Deferred[Response | Request]:
        assert self.slot is not None  # typing

        self.slot.add_request(request)

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
            assert self.slot is not None
            self.slot.nextcall.schedule()
            return _

        assert self.spider is not None
        dwld: Deferred[Response | Request] = self.downloader.fetch(request, self.spider)
        dwld.addCallback(_on_success)
        dwld.addBoth(_on_complete)
        return dwld

    @inlineCallbacks
    def open_spider(
        self,
        spider: Spider,
        start_requests: Iterable[Request] = (),
        close_if_idle: bool = True,
    ) -> Generator[Deferred[Any], Any, None]:
        if self.slot is not None:
            raise RuntimeError(f"No free spider slot when opening {spider.name!r}")
        logger.info("Spider opened", extra={"spider": spider})
        nextcall = CallLaterOnce(self._next_request)
        scheduler = build_from_crawler(self.scheduler_cls, self.crawler)
        start_requests = yield self.scraper.spidermw.process_start_requests(
            start_requests, spider
        )
        self.slot = Slot(start_requests, close_if_idle, nextcall, scheduler)
        self.spider = spider
        if hasattr(scheduler, "open"):
            if d := scheduler.open(spider):
                yield d
        yield self.scraper.open_spider(spider)
        assert self.crawler.stats
        self.crawler.stats.open_spider(spider)
        yield self.signals.send_catch_log_deferred(signals.spider_opened, spider=spider)
        self.slot.nextcall.schedule()
        self.slot.heartbeat.start(5)

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
        if self.slot is None:
            raise RuntimeError("Engine slot not assigned")

        if self.slot.closing is not None:
            return self.slot.closing

        logger.info(
            "Closing spider (%(reason)s)", {"reason": reason}, extra={"spider": spider}
        )

        dfd = self.slot.close()

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

        if hasattr(self.slot.scheduler, "close"):
            dfd.addBoth(lambda _: cast(Slot, self.slot).scheduler.close(reason))
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
