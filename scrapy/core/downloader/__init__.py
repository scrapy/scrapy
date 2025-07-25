from __future__ import annotations

import random
import warnings
from collections import deque
from datetime import datetime
from time import time
from typing import TYPE_CHECKING, Any, cast

from twisted.internet.defer import Deferred, inlineCallbacks

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
from scrapy.utils.defer import (
    _defer_sleep_async,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from collections.abc import Generator

    from twisted.internet.task import LoopingCall

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings
    from scrapy.signalmanager import SignalManager


class Slot:
    """Downloader slot"""

    def __init__(
        self,
        concurrency: int,
        delay: float,
        randomize_delay: bool,
    ):
        self.concurrency: int = concurrency
        self.delay: float = delay
        self.randomize_delay: bool = randomize_delay

        self.active: set[Request] = set()
        self.queue: deque[tuple[Request, Deferred[Response]]] = deque()
        self.transferring: set[Request] = set()
        self.lastseen: float = 0
        self.latercall: CallLaterResult | None = None

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

    def __repr__(self) -> str:
        cls_name = self.__class__.__name__
        return (
            f"{cls_name}(concurrency={self.concurrency!r}, "
            f"delay={self.delay:.2f}, "
            f"randomize_delay={self.randomize_delay!r})"
        )

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

    if hasattr(spider, "max_concurrent_requests"):
        concurrency = spider.max_concurrent_requests

    return concurrency, delay


class Downloader:
    DOWNLOAD_SLOT = "download_slot"

    def __init__(self, crawler: Crawler):
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
        self._slot_gc_loop: AsyncioLoopingCall | LoopingCall = create_looping_call(
            self._slot_gc
        )
        self._slot_gc_loop.start(60)
        self.per_slot_settings: dict[str, dict[str, Any]] = self.settings.getdict(
            "DOWNLOAD_SLOTS"
        )

    @inlineCallbacks
    def fetch(
        self, request: Request, spider: Spider
    ) -> Generator[Deferred[Any], Any, Response | Request]:
        self.active.add(request)
        try:
            return (
                yield self.middleware.download(self._enqueue_request, request, spider)
            )
        finally:
            self.active.remove(request)

    def needs_backout(self) -> bool:
        return len(self.active) >= self.total_concurrency

    def _get_slot(self, request: Request, spider: Spider) -> tuple[str, Slot]:
        key = self.get_slot_key(request)
        if key not in self.slots:
            slot_settings = self.per_slot_settings.get(key, {})
            conc = (
                self.ip_concurrency if self.ip_concurrency else self.domain_concurrency
            )
            conc, delay = _get_concurrency_delay(conc, spider, self.settings)
            conc, delay = (
                slot_settings.get("concurrency", conc),
                slot_settings.get("delay", delay),
            )
            randomize_delay = slot_settings.get("randomize_delay", self.randomize_delay)
            new_slot = Slot(conc, delay, randomize_delay)
            self.slots[key] = new_slot

        return key, self.slots[key]

    def get_slot_key(self, request: Request) -> str:
        if self.DOWNLOAD_SLOT in request.meta:
            return cast("str", request.meta[self.DOWNLOAD_SLOT])

        key = urlparse_cached(request).hostname or ""
        if self.ip_concurrency:
            key = dnscache.get(key, key)

        return key

    def _get_slot_key(self, request: Request, spider: Spider | None) -> str:
        warnings.warn(
            "Use of this protected method is deprecated. Consider using its corresponding public method get_slot_key() instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self.get_slot_key(request)

    @inlineCallbacks
    def _enqueue_request(
        self, request: Request, spider: Spider
    ) -> Generator[Deferred[Any], Any, Response]:
        key, slot = self._get_slot(request, spider)
        request.meta[self.DOWNLOAD_SLOT] = key
        slot.active.add(request)
        self.signals.send_catch_log(
            signal=signals.request_reached_downloader, request=request, spider=spider
        )
        d: Deferred[Response] = Deferred()
        slot.queue.append((request, d))
        self._process_queue(spider, slot)
        try:
            return (yield d)
        finally:
            slot.active.remove(request)

    def _process_queue(self, spider: Spider, slot: Slot) -> None:
        if slot.latercall:
            # block processing until slot.latercall is called
            return

        # Delay queue processing if a download_delay is configured
        now = time()
        delay = slot.download_delay()
        if delay:
            penalty = delay - now + slot.lastseen
            if penalty > 0:
                slot.latercall = call_later(penalty, self._latercall, spider, slot)
                return

        # Process enqueued requests if there are free slots to transfer for this slot
        while slot.queue and slot.free_transfer_slots() > 0:
            slot.lastseen = now
            request, deferred = slot.queue.popleft()
            dfd = deferred_from_coro(self._download(slot, request, spider))
            dfd.chainDeferred(deferred)
            # prevent burst if inter-request delays were configured
            if delay:
                self._process_queue(spider, slot)
                break

    def _latercall(self, spider: Spider, slot: Slot) -> None:
        slot.latercall = None
        self._process_queue(spider, slot)

    async def _download(self, slot: Slot, request: Request, spider: Spider) -> Response:
        # The order is very important for the following logic. Do not change!
        slot.transferring.add(request)
        try:
            # 1. Download the response
            response: Response = await maybe_deferred_to_future(
                self.handlers.download_request(request, spider)
            )
            # 2. Notify response_downloaded listeners about the recent download
            # before querying queue for next request
            self.signals.send_catch_log(
                signal=signals.response_downloaded,
                response=response,
                request=request,
                spider=spider,
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
            self._process_queue(spider, slot)
            self.signals.send_catch_log(
                signal=signals.request_left_downloader, request=request, spider=spider
            )

    def close(self) -> None:
        self._slot_gc_loop.stop()
        for slot in self.slots.values():
            slot.close()

    def _slot_gc(self, age: float = 60) -> None:
        mintime = time() - age
        for key, slot in list(self.slots.items()):
            if not slot.active and slot.lastseen + slot.delay < mintime:
                self.slots.pop(key).close()
