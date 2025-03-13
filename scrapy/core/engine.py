"""
This is the Scrapy engine which controls the Scheduler, Downloader and Spider.

For more information see docs/topics/architecture.rst

"""

from __future__ import annotations

import logging
from time import time
from typing import TYPE_CHECKING, Any, TypeVar, cast

from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.task import LoopingCall
from twisted.python.failure import Failure

from scrapy import signals
from scrapy.core.scraper import Scraper, _HandleOutputDeferred
from scrapy.exceptions import CloseSpider, DontCloseSpider, IgnoreRequest
from scrapy.http import Request, Response
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.log import failure_to_exc_info, logformatter_adapter
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.reactor import CallLaterOnce

from ._seeding import SeedingPolicy

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Callable, Generator

    from scrapy.core.downloader import Downloader
    from scrapy.core.scheduler import BaseScheduler
    from scrapy.crawler import Crawler
    from scrapy.logformatter import LogFormatter
    from scrapy.settings import BaseSettings, Settings
    from scrapy.signalmanager import SignalManager
    from scrapy.spiders import Spider


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class _SeedingPolicyChange(Exception):
    pass


class _Slot:
    def __init__(
        self,
        close_if_idle: bool,
        nextcall: CallLaterOnce[Deferred[None]],
        scheduler: BaseScheduler,
    ) -> None:
        self.closing: Deferred[None] | None = None
        self.inprogress: set[Request] = set()
        self.close_if_idle: bool = close_if_idle
        self.nextcall: CallLaterOnce[Deferred[None]] = nextcall
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
        self._load_seeding_policy()
        self._seeds: AsyncIterable[Any] | None = None
        self._waiting_for_seed: bool = False

    def _load_seeding_policy(self) -> None:
        try:
            self._seeding_policy = SeedingPolicy(self.settings["SEEDING_POLICY"])
        except ValueError:
            supported_values = ", ".join(policy.value for policy in SeedingPolicy)
            raise ValueError(
                f"The value of the SEEDING_POLICY setting "
                f"({self.settings['SEEDING_POLICY']!r}) is not supported. "
                f"Supported values: {supported_values}."
            )

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

    @inlineCallbacks
    def _process_next_seed(self):
        if self._waiting_for_seed:
            return
        self._waiting_for_seed = True
        try:
            seed = yield deferred_from_coro(self._seeds.__anext__())
        except StopAsyncIteration:
            self._seeds = None
        except CloseSpider:
            self._seeds = None
            raise
        except Exception:
            self._seeds = None
            logger.error(
                "Error while reading seeds",
                exc_info=True,
                extra={"spider": self.spider},
            )
        else:
            if isinstance(seed, Request):
                self.crawl(seed)
                if (
                    self._seeding_policy is not SeedingPolicy.front_load
                    and not self._needs_backout()
                ):
                    self._start_scheduled_request()
            elif isinstance(seed, (str, SeedingPolicy)):
                try:
                    self._seeding_policy = SeedingPolicy(seed)
                except ValueError:
                    valid_policy_strings = ", ".join(
                        policy.value for policy in SeedingPolicy
                    )
                    logger.error(
                        f"Seed {seed!r} has been ignored. Seeds of {str} type "
                        f"must be valid seeding policies "
                        f"({valid_policy_strings})."
                    )
                    self._slot.nextcall.schedule()
                else:
                    raise _SeedingPolicyChange
            else:
                self.scraper.start_itemproc(seed, response=None)
                self._slot.nextcall.schedule()
        finally:
            self._waiting_for_seed = False
        if self._seeding_policy is SeedingPolicy.front_load and self._seeds is None:
            self._slot.nextcall.schedule()

    @inlineCallbacks
    def _start_next_requests(self) -> Generator[Deferred[Any], Any, None]:
        if self._slot is None or self._slot.closing is not None or self.paused:
            return

        try:
            if self._seeding_policy in {SeedingPolicy.idle, SeedingPolicy.lazy}:
                while not self._needs_backout():
                    if self._start_scheduled_request() is None:
                        break
                if (
                    self._seeds is not None
                    and not self._needs_backout()
                    and (
                        self._seeding_policy is not SeedingPolicy.idle
                        or (not self._waiting_for_seed and not self.downloader.active)
                    )
                ):
                    yield self._process_next_seed()
            else:
                assert self._seeding_policy in {
                    SeedingPolicy.front_load,
                    SeedingPolicy.greedy,
                }
                if self._seeds is not None:
                    if not self._needs_backout():
                        yield self._process_next_seed()
                else:
                    while not self._needs_backout():
                        if self._start_scheduled_request() is None:
                            break
        except _SeedingPolicyChange:
            self._slot.nextcall.schedule()
            return
        except CloseSpider as exception:
            assert self.spider is not None  # typing
            self.close_spider(self.spider, reason=exception.reason)
            return

        if self.spider_is_idle() and self._slot.close_if_idle:
            self._spider_idle()

    def _needs_backout(self) -> bool:
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

        request = self._slot.scheduler.next_request()
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
        if self._seeds is not None:  # not all start requests are handled
            return False
        return not self._slot.scheduler.has_pending_requests()

    def crawl(self, request: Request) -> None:
        """Inject the request into the spider <-> downloader pipeline"""
        if self.spider is None:
            raise RuntimeError(f"No open spider to crawl: {request}")
        self._schedule_request(request, self.spider)
        self._slot.nextcall.schedule()  # type: ignore[union-attr]

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
        if not self._slot.scheduler.enqueue_request(request):  # type: ignore[union-attr]
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

    @inlineCallbacks
    def open_spider(
        self,
        spider: Spider,
        close_if_idle: bool = True,
    ) -> Generator[Deferred[Any], Any, None]:
        if self._slot is not None:
            raise RuntimeError(f"No free spider slot when opening {spider.name!r}")
        logger.info("Spider opened", extra={"spider": spider})
        nextcall = CallLaterOnce(self._start_next_requests)
        scheduler = build_from_crawler(self.scheduler_cls, self.crawler)
        self._seeds = yield self.scraper.spidermw.process_seeds(spider)
        self._slot = _Slot(close_if_idle, nextcall, scheduler)
        self.spider = spider
        if hasattr(scheduler, "open") and (d := scheduler.open(spider)):
            yield d
        yield self.scraper.open_spider(spider)
        assert self.crawler.stats
        self.crawler.stats.open_spider(spider)
        yield self.signals.send_catch_log_deferred(signals.spider_opened, spider=spider)
        self._slot.nextcall.schedule()
        self._slot.heartbeat.start(self._SLOT_HEARTBEAT_INTERVAL)

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

        dfd.addBoth(lambda _: setattr(self, "slot", None))
        dfd.addErrback(log_failure("Error while unassigning slot"))

        dfd.addBoth(lambda _: setattr(self, "spider", None))
        dfd.addErrback(log_failure("Error while unassigning spider"))

        dfd.addBoth(lambda _: self._spider_closed_callback(spider))

        return dfd
