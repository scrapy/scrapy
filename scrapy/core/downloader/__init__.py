from __future__ import annotations

import random
import warnings
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from time import monotonic
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.resolver import dnscache
from scrapy.settings import SETTINGS_PRIORITIES
from scrapy.utils.asyncio import (
    AsyncioLoopingCall,
    CallLaterResult,
    call_later,
    create_looping_call,
)
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _process_pending_io,
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


@dataclass(slots=True, eq=False)
class Slot:
    """Downloader slot"""

    concurrency: int
    delay: float
    jitter: float

    active: set[Request] = field(default_factory=set, init=False, repr=False)
    queue: deque[tuple[Request, Deferred[Response]]] = field(
        default_factory=deque, init=False, repr=False
    )
    transferring: set[Request] = field(default_factory=set, init=False, repr=False)
    lastseen: float = field(default=0, init=False, repr=False)
    latercall: CallLaterResult | None = field(default=None, init=False, repr=False)

    # Hand-written to accept the deprecated randomize_delay parameter, which
    # means it also has to initialize the fields above.
    def __init__(
        self,
        concurrency: int,
        delay: float,
        jitter: float | None = None,
        randomize_delay: bool | None = None,
    ) -> None:
        if isinstance(jitter, bool):
            # randomize_delay used to be the third positional parameter, and a
            # boolean would otherwise pass for a magnitude, True meaning ±100%.
            jitter, randomize_delay = None, jitter
        if randomize_delay is not None:
            warnings.warn(
                "The randomize_delay parameter of Slot is deprecated, use "
                "jitter instead: it takes the magnitude of the random variation "
                "as a number, e.g. 0.5 for the ±50% that randomize_delay "
                "enables, or 0 to disable it.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        self.concurrency = concurrency
        self.delay = delay
        self.jitter = jitter if jitter is not None else 0.5 * bool(randomize_delay)
        self.active = set()
        self.queue = deque()
        self.transferring = set()
        self.lastseen = 0
        self.latercall = None

    @property
    def randomize_delay(self) -> bool:
        warnings.warn(
            "Slot.randomize_delay is deprecated, use Slot.jitter instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return bool(self.jitter)

    @randomize_delay.setter
    def randomize_delay(self, value: bool) -> None:
        warnings.warn(
            "Slot.randomize_delay is deprecated, use Slot.jitter instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self.jitter = 0.5 if value else 0.0

    def free_transfer_slots(self) -> int:
        return self.concurrency - len(self.transferring)

    def download_delay(self) -> float:
        if not self.jitter:
            return self.delay
        # A jitter above 1 would reach into negative delays, floored at 0.
        return max(0.0, self.delay * (1 + random.uniform(-self.jitter, self.jitter)))  # noqa: S311

    def close(self) -> None:
        if self.latercall:
            self.latercall.cancel()
            self.latercall = None

    def __str__(self) -> str:
        return (
            f"<downloader.Slot concurrency={self.concurrency!r} "
            f"delay={self.delay:.2f} jitter={self.jitter!r} "
            f"len(active)={len(self.active)} len(queue)={len(self.queue)} "
            f"len(transferring)={len(self.transferring)} "
            f"lastseen={datetime.fromtimestamp(self.lastseen).isoformat()}>"
        )


def _default_jitter(settings: BaseSettings) -> float:
    """Return the magnitude of the random variation to apply to the delay of
    slots that do not set their own ``jitter``: :setting:`DOWNLOAD_DELAY_JITTER`,
    or the deprecated ``RANDOMIZE_DOWNLOAD_DELAY`` when set at a higher
    :ref:`priority <populating-settings>`, mapped to the historical ±50% or
    none.

    Warns when ``RANDOMIZE_DOWNLOAD_DELAY`` is set, so it is called once per
    crawl, from :meth:`Downloader.__init__`. Both defaults mean the same ±50%,
    so a crawl that sets neither needs no warning.
    """
    randomize_priority = settings.getpriority("RANDOMIZE_DOWNLOAD_DELAY") or 0
    if randomize_priority <= SETTINGS_PRIORITIES["default"]:
        return settings.getfloat("DOWNLOAD_DELAY_JITTER")
    warnings.warn(
        "The RANDOMIZE_DOWNLOAD_DELAY setting is deprecated, use "
        "DOWNLOAD_DELAY_JITTER instead: it takes the magnitude of the random "
        "variation as a number, e.g. 0.5 for the ±50% that "
        "RANDOMIZE_DOWNLOAD_DELAY enables, or 0 to disable it.",
        category=ScrapyDeprecationWarning,
        stacklevel=3,
    )
    if randomize_priority > (settings.getpriority("DOWNLOAD_DELAY_JITTER") or 0):
        return 0.5 if settings.getbool("RANDOMIZE_DOWNLOAD_DELAY") else 0.0
    return settings.getfloat("DOWNLOAD_DELAY_JITTER")


def _slot_jitter(slot_settings: dict[str, Any], default: float) -> float:
    """Return the jitter of a :setting:`DOWNLOAD_SLOTS` entry, from its
    ``jitter`` key, its deprecated ``randomize_delay`` key, or *default*."""
    if "jitter" in slot_settings:
        return float(slot_settings["jitter"])
    if "randomize_delay" in slot_settings:
        warnings.warn(
            "The randomize_delay key of the DOWNLOAD_SLOTS setting is "
            "deprecated, use jitter instead: it takes the magnitude of the "
            "random variation as a number, e.g. 0.5 for the ±50% that "
            "randomize_delay enables, or 0 to disable it.",
            category=ScrapyDeprecationWarning,
            stacklevel=3,
        )
        return 0.5 if slot_settings["randomize_delay"] else 0.0
    return default


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
        self._jitter: float = _default_jitter(self.settings)
        self.middleware: DownloaderMiddlewareManager = build_from_crawler(
            DownloaderMiddlewareManager, crawler
        )
        self._slot_gc_loop: AsyncioLoopingCall | LoopingCall | None = None
        self.per_slot_settings: dict[str, dict[str, Any]] = self.settings.getdict(
            "DOWNLOAD_SLOTS"
        )

    @property
    def randomize_delay(self) -> bool:
        warnings.warn(
            "Downloader.randomize_delay is deprecated, use the "
            "DOWNLOAD_DELAY_JITTER setting instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return bool(self._jitter)

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
            new_slot = Slot(conc, delay, _slot_jitter(slot_settings, self._jitter))
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
            await _process_pending_io()
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
