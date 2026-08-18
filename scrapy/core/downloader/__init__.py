from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from time import monotonic, time
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
    sleep,
)
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _defer_sleep_async,
    _schedule_coro,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from collections.abc import Generator

    from twisted.internet.task import LoopingCall

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings
    from scrapy.signalmanager import SignalManager


# Request.meta key holding the delay of a request and the time before which it
# must not be sent because of it. The deadline is a wall-clock time, so that it
# survives a crawl being resumed from a disk queue.
_DELAY_DEADLINE_META_KEY = "_delay_deadline"


def _start_delay_countdown(request: Request) -> None:
    """Turn the ``delay`` meta key of *request*, if any, into a deadline.

    Requests are stamped as they are scheduled, so that their delay runs while
    they wait for their turn instead of only once they get it.

    ``delay`` is consumed, so that a copy of the request, such as a retry or a
    redirect, is not held again, while setting the key again asks for a new
    delay. What the request has been through is left on ``delayed``.
    """
    delay = request.meta.pop("delay", None)
    if not delay:
        return
    delay = float(delay)
    request.meta[_DELAY_DEADLINE_META_KEY] = (delay, time() + delay)
    request.meta["delayed"] = [*request.meta.get("delayed", []), delay]


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
        # Default delay of new slots. AutoThrottle overrides it to apply
        # AUTOTHROTTLE_START_DELAY.
        self._delay: float = self.settings.getfloat("DOWNLOAD_DELAY")
        self.randomize_delay: bool = self.settings.getbool("RANDOMIZE_DOWNLOAD_DELAY")
        self.middleware: DownloaderMiddlewareManager = build_from_crawler(
            DownloaderMiddlewareManager, crawler
        )
        self._slot_gc_loop: AsyncioLoopingCall | LoopingCall | None = None
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
            result: Response | Request = yield (
                deferred_from_coro(
                    self.middleware.download_async(self._enqueue_request, request)
                )
            )
            return result
        finally:
            self.active.remove(request)

    def needs_backout(self) -> bool:
        # A total concurrency of 0 means no limit.
        return 0 < self.total_concurrency <= len(self.active)

    @_warn_spider_arg
    def _get_slot(
        self, request: Request, spider: Spider | None = None
    ) -> tuple[str, Slot]:
        key = self.get_slot_key(request)
        if key not in self.slots:
            slot_settings = self.per_slot_settings.get(key, {})
            conc = slot_settings.get(
                "concurrency", self.ip_concurrency or self.domain_concurrency
            )
            delay = slot_settings.get("delay", self._delay)
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

    async def _delay_request(self, request: Request) -> None:
        """Hold *request* until the deadline of its ``delay`` meta key.

        The wait happens before the request gets a slot, so it does not take a
        slot concurrency spot.
        """
        # A request that skipped the scheduler, e.g. one from
        # ExecutionEngine.download_async(), starts its countdown here.
        _start_delay_countdown(request)
        countdown = request.meta.pop(_DELAY_DEADLINE_META_KEY, None)
        if countdown is None:
            return
        delay, deadline = countdown
        # A deadline further away than the delay means the clock moved backwards
        # since it was set, which takes a crawl resumed from a disk queue, e.g.
        # on a machine with a lagging clock. Capping keeps the wait to what the
        # delay asked for.
        wait = min(deadline - time(), delay)
        if wait > 0:
            await sleep(wait)

    # passed as download_func into self.middleware.download() in self.fetch()
    async def _enqueue_request(self, request: Request) -> Response:
        await self._delay_request(request)
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
