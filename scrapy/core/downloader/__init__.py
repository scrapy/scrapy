from __future__ import annotations

import gc
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger
from time import monotonic
from typing import TYPE_CHECKING, Any
from warnings import warn

try:
    from win_precise_time import time
except ImportError:
    from time import time

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.resolver import dnscache
from scrapy.utils.asyncio import (
    AsyncioLoopingCall,
    CallLaterResult,
    call_later,
    create_looping_call,
)
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _defer_sleep_async,
    _schedule_coro,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.deprecate import warn_on_deprecated_spider_attribute
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from collections.abc import Generator

    from twisted.internet.task import LoopingCall

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings
    from scrapy.signalmanager import SignalManager

logger = getLogger(__name__)


@dataclass(slots=True, eq=False)
class Slot:
    """Downloader slot"""

    concurrency: int
    delay: float
    randomize_delay: bool

    active: set[Request] = field(default_factory=set, init=False, repr=False)
    queue: deque[tuple[Request, Deferred[Response]]] = field(
        default_factory=deque, init=False, repr=False
    )
    transferring: set[Request] = field(default_factory=set, init=False, repr=False)
    lastseen: float = field(default=0, init=False, repr=False)
    latercall: CallLaterResult | None = field(default=None, init=False, repr=False)

    def free_transfer_slots(self) -> int:
        return self.concurrency - len(self.transferring)

    def download_delay(self) -> float:
        if self.randomize_delay:
            return random.uniform(0.5 * self.delay, 1.5 * self.delay)  # noqa: S311
        return self.delay

    def close(self) -> None:
        if self.latercall:
            self.latercall.cancel()
            self.latercall = None

    def __str__(self) -> str:
        return (
            f"<downloader.Slot concurrency={self.concurrency!r} "
            f"delay={self.delay:.2f} randomize_delay={self.randomize_delay!r} "
            f"len(active)={len(self.active)} len(queue)={len(self.queue)} "
            f"len(transferring)={len(self.transferring)} "
            f"lastseen={datetime.fromtimestamp(self.lastseen).isoformat()}>"
        )


def _get_concurrency_delay(
    concurrency: int, spider: Spider, settings: BaseSettings
) -> tuple[int, float]:
    delay: float = settings.getfloat("DOWNLOAD_DELAY")
    if hasattr(spider, "download_delay"):
        delay = spider.download_delay

    if hasattr(spider, "max_concurrent_requests"):  # pragma: no cover
        warn_on_deprecated_spider_attribute(
            "max_concurrent_requests", "CONCURRENT_REQUESTS"
        )
        concurrency = spider.max_concurrent_requests

    return concurrency, delay


class Downloader:
    DOWNLOAD_SLOT = "download_slot"
    _SLOT_GC_INTERVAL: float = 60.0  # seconds

    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler
        self.settings: BaseSettings = crawler.settings
        self.signals: SignalManager = crawler.signals
        self.slots: dict[str, Slot] = {}
        self.active: set[Request] = set()
        self.handlers: DownloadHandlers = DownloadHandlers(crawler)
        self.total_concurrency: int = self.settings.getint("CONCURRENT_REQUESTS")
        self.domain_concurrency: int = self.settings.getint(
            "CONCURRENT_REQUESTS_PER_DOMAIN"
        )
        self.ip_concurrency: int = self.settings.getint("CONCURRENT_REQUESTS_PER_IP")
        self.randomize_delay: bool = self.settings.getbool("RANDOMIZE_DOWNLOAD_DELAY")
        self.middleware: DownloaderMiddlewareManager = (
            DownloaderMiddlewareManager.from_crawler(crawler)
        )
        self._slot_gc_loop: AsyncioLoopingCall | LoopingCall | None = None
        self.per_slot_settings: dict[str, dict[str, Any]] = self.settings.getdict(
            "DOWNLOAD_SLOTS"
        )
        self._stats = crawler.stats
        self._last_backout = (None, None)

        deprecated_setting_priority = self.settings.getpriority(
            "SCRAPER_SLOT_MAX_ACTIVE_SIZE"
        )
        assert deprecated_setting_priority is not None
        if deprecated_setting_priority > 0:
            warn(
                (
                    "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated, "
                    "use RESPONSE_MAX_ACTIVE_SIZE instead."
                ),
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
        setting_priority = self.settings.getpriority("RESPONSE_MAX_ACTIVE_SIZE")
        assert setting_priority is not None
        if setting_priority >= deprecated_setting_priority:
            self._response_max_active_size = self.settings.getint(
                "RESPONSE_MAX_ACTIVE_SIZE"
            )
        else:
            self._response_max_active_size = self.settings.getint(
                "SCRAPER_SLOT_MAX_ACTIVE_SIZE"
            )
        self._response_max_active_size_warned = False

    @inlineCallbacks
    @_warn_spider_arg
    def fetch(
        self, request: Request, spider: Spider | None = None
    ) -> Generator[Deferred[Any], Any, Response | Request]:
        self.active.add(request)
        try:
            result: Response | Request = yield (
                deferred_from_coro(
                    self.middleware.download_async(self._enqueue_request, request)
                )
            )
            return result
        finally:
            self.active.remove(request)

    def _record_backout(self, reason):
        last_reason, last_reason_start_time = self._last_backout
        if last_reason == reason:
            return
        current_time = time()
        if last_reason is not None:
            last_reason_seconds = current_time - last_reason_start_time
            self._stats.inc_value("request_backout_seconds/total", last_reason_seconds)
            self._stats.inc_value(
                f"request_backout_seconds/{last_reason}", last_reason_seconds
            )
        self._last_backout = (reason, current_time)

    def needs_backout(self) -> bool:
        if len(self.active) >= self.total_concurrency:
            self._record_backout("concurrency")
            return True
        if (
            self._response_max_active_size
            and self.middleware.response_active_size >= self._response_max_active_size
        ):
            if not self._response_max_active_size_warned:
                self._response_max_active_size_warned = True
                logger.info(
                    f"The active response size, i.e. the total size of all "
                    f"bodies from responses that have been processed by "
                    f"downloader middlewares and remain in memory, is "
                    f"{self.middleware.response_active_size} B. The "
                    f"RESPONSE_MAX_ACTIVE_SIZE setting sets its maximum value "
                    f"at {self._response_max_active_size} B. No more requests "
                    f"will be processed until active response size lowers. If "
                    f"your memory allows it, you may increase "
                    f"RESPONSE_MAX_ACTIVE_SIZE, which should increase your "
                    f"crawl speed. If your code keeps non-weak references to "
                    f"Response objects, e.g. in (scheduled) requests or in a "
                    f"container within a component, your crawl might get "
                    f"stuck indefinitely; you can set "
                    f"RESPONSE_MAX_ACTIVE_SIZE to 0 to disable this limit, "
                    f"but then your code might run out of memory. This "
                    f"message will only appear the first time this happens. "
                    f"To learn how often request processing has been paused "
                    f"during a crawl for this reason, see the "
                    f"request_backouts/response_max_active_size stat."
                )
            self._record_backout("response_max_active_size")
            # Force the garbage collection of response objects. Necessary for
            # PyPy, which is lazier when it comes to garbage collection.
            gc.collect()
            return True
        self._record_backout(None)
        return False

    @_warn_spider_arg
    def _get_slot(
        self, request: Request, spider: Spider | None = None
    ) -> tuple[str, Slot]:
        key = self.get_slot_key(request)
        if key not in self.slots:
            assert self.crawler.spider
            slot_settings = self.per_slot_settings.get(key, {})
            conc = self.ip_concurrency or self.domain_concurrency
            conc, delay = _get_concurrency_delay(
                conc, self.crawler.spider, self.settings
            )
            conc, delay = (
                slot_settings.get("concurrency", conc),
                slot_settings.get("delay", delay),
            )
            randomize_delay = slot_settings.get("randomize_delay", self.randomize_delay)
            new_slot = Slot(conc, delay, randomize_delay)
            self.slots[key] = new_slot
            self._start_slot_gc()

        return key, self.slots[key]

    def get_slot_key(self, request: Request) -> str:
        meta_slot: str | None = request.meta.get(self.DOWNLOAD_SLOT)
        if meta_slot is not None:
            return meta_slot

        key = urlparse_cached(request).hostname or ""
        if self.ip_concurrency:
            key = dnscache.get(key, key)

        return key

    # passed as download_func into self.middleware.download() in self.fetch()
    async def _enqueue_request(self, request: Request) -> Response:
        key, slot = self._get_slot(request)
        request.meta[self.DOWNLOAD_SLOT] = key
        slot.active.add(request)
        self.signals.send_catch_log(
            signal=signals.request_reached_downloader,
            request=request,
            spider=self.crawler.spider,
        )
        d: Deferred[Response] = Deferred()
        slot.queue.append((request, d))
        self._process_queue(slot)
        try:
            return await maybe_deferred_to_future(d)  # fired in _wait_for_download()
        finally:
            slot.active.remove(request)

    def _process_queue(self, slot: Slot) -> None:
        if slot.latercall:
            # block processing until slot.latercall is called
            return

        # Delay queue processing if a download_delay is configured
        now = monotonic()
        delay = slot.download_delay()
        if delay:
            penalty = delay - now + slot.lastseen
            if penalty > 0:
                slot.latercall = call_later(penalty, self._latercall, slot)
                return

        # Process enqueued requests if there are free slots to transfer for this slot
        while slot.queue and slot.free_transfer_slots() > 0:
            slot.lastseen = now
            request, queue_dfd = slot.queue.popleft()
            _schedule_coro(self._wait_for_download(slot, request, queue_dfd))
            # prevent burst if inter-request delays were configured
            if delay:
                self._process_queue(slot)
                break

    def _latercall(self, slot: Slot) -> None:
        slot.latercall = None
        self._process_queue(slot)

    async def _download(self, slot: Slot, request: Request) -> Response:
        # The order is very important for the following logic. Do not change!
        slot.transferring.add(request)
        try:
            # 1. Download the response
            response: Response = await self.handlers.download_request_async(request)
            # 2. Notify response_downloaded listeners about the recent download
            # before querying queue for next request
            self.signals.send_catch_log(
                signal=signals.response_downloaded,
                response=response,
                request=request,
                spider=self.crawler.spider,
            )
            return response
        except Exception:
            await _defer_sleep_async()
            raise
        finally:
            # 3. After response arrives, remove the request from transferring
            # state to free up the transferring slot so it can be used by the
            # following requests (perhaps those which came from the downloader
            # middleware itself)
            slot.transferring.remove(request)
            self._process_queue(slot)
            self.signals.send_catch_log(
                signal=signals.request_left_downloader,
                request=request,
                spider=self.crawler.spider,
            )

    async def _wait_for_download(
        self, slot: Slot, request: Request, queue_dfd: Deferred[Response]
    ) -> None:
        try:
            response = await self._download(slot, request)
        except Exception:
            queue_dfd.errback(Failure())
        else:
            queue_dfd.callback(response)  # awaited in _enqueue_request()

    def close(self) -> None:
        self._stop_slot_gc()
        for slot in self.slots.values():
            slot.close()
        self._record_backout(None)

    def _slot_gc(self, age: float = 60) -> None:
        mintime = monotonic() - age
        for key, slot in list(self.slots.items()):
            if not slot.active and slot.lastseen + slot.delay < mintime:
                self.slots.pop(key).close()

    def _start_slot_gc(self) -> None:
        if self._slot_gc_loop:
            return
        self._slot_gc_loop = create_looping_call(self._slot_gc)
        self._slot_gc_loop.start(self._SLOT_GC_INTERVAL, now=False)

    def _stop_slot_gc(self) -> None:
        if self._slot_gc_loop:
            self._slot_gc_loop.stop()
            self._slot_gc_loop = None
