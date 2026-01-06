from __future__ import annotations

import random
from collections import deque
from datetime import datetime
from time import time
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
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

    if hasattr(spider, "max_concurrent_requests"):  # pragma: no cover
        warn_on_deprecated_spider_attribute(
            "max_concurrent_requests", "CONCURRENT_REQUESTS"
        )
        concurrency = spider.max_concurrent_requests

    return concurrency, delay


class Downloader:
    DOWNLOAD_SLOT = "download_slot"

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
        self._slot_gc_loop: AsyncioLoopingCall | LoopingCall = create_looping_call(
            self._slot_gc
        )
        self._slot_gc_loop.start(60)
        self.per_slot_settings: dict[str, dict[str, Any]] = self.settings.getdict(
            "DOWNLOAD_SLOTS"
        )

    @inlineCallbacks
    @_warn_spider_arg
    def fetch(
        self, request: Request, spider: Spider | None = None
    ) -> Generator[Deferred[Any], Any, Response | Request]:
        self.active.add(request)
        try:
            return (
                yield deferred_from_coro(
                    self.middleware.download_async(self._enqueue_request, request)
                )
            )
        finally:
            self.active.remove(request)

    def needs_backout(self) -> bool:
        return len(self.active) >= self.total_concurrency

    @_warn_spider_arg
    def _get_slot(
        self, request: Request, spider: Spider | None = None
    ) -> tuple[str, Slot]:
        key = self.get_slot_key(request)
        if key not in self.slots:
            assert self.crawler.spider
            slot_settings = self.per_slot_settings.get(key, {})
            conc = (
                self.ip_concurrency if self.ip_concurrency else self.domain_concurrency
            )
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

        return key, self.slots[key]

    def get_slot_key(self, request: Request) -> str:
        if (meta_slot := request.meta.get(self.DOWNLOAD_SLOT)) is not None:
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
        now = time()
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
        self._slot_gc_loop.stop()
        for slot in self.slots.values():
            slot.close()

    def _slot_gc(self, age: float = 60) -> None:
        mintime = time() - age
        for key, slot in list(self.slots.items()):
            if not slot.active and slot.lastseen + slot.delay < mintime:
                self.slots.pop(key).close()
