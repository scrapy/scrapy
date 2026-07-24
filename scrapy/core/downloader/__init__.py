from __future__ import annotations

import random
import warnings
from collections import deque
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import inlineCallbacks

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import _defer_sleep_async, deferred_from_coro
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from collections.abc import Generator

    from twisted.internet.defer import Deferred

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings
    from scrapy.signalmanager import SignalManager
    from scrapy.throttler import ThrottlerProtocol, ThrottlingScopeManagerProtocol
    from scrapy.utils.asyncio import CallLaterResult


@dataclass(slots=True, eq=False)
class _Slot:
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


Slot = create_deprecated_class(
    "Slot",
    _Slot,
    old_class_path="scrapy.core.downloader.Slot",
    subclass_warn_message=("{cls} inherits from the deprecated Slot class."),
    instance_warn_message=("The Slot class is deprecated."),
)


class _DeprecatedSlotView:
    """Deprecated per-domain slot view backed by the downloader and throttler."""

    __slots__ = ("_downloader", "_key", "_scope")

    def __init__(
        self,
        downloader: Downloader,
        key: str,
        scope: ThrottlingScopeManagerProtocol,
    ) -> None:
        self._downloader = downloader
        self._key = key
        self._scope = scope

    @property
    def active(self) -> set[Request]:
        return {
            r
            for r in self._downloader.active
            if r.meta.get(Downloader.DOWNLOAD_SLOT) == self._key
        }

    @property
    def transferring(self) -> set[Request]:
        return {
            r
            for r in self._downloader._transferring
            if r.meta.get(Downloader.DOWNLOAD_SLOT) == self._key
        }

    # This deprecated view reads throttling scope state from private attributes
    # of the default scope manager rather than through the scope manager
    # protocol: these are read-only compatibility accessors, so keeping them off
    # the protocol avoids forcing custom THROTTLING_SCOPE_MANAGER implementations
    # to provide members that only exist to feed this shim. A custom manager that
    # lacks the attribute simply falls back to the historical default.
    @property
    def lastseen(self) -> float:
        return getattr(self._scope, "_last_seen", None) or 0.0

    @property
    def delay(self) -> float:
        return getattr(self._scope, "_delay", 0.0)

    @delay.setter
    def delay(self, value: float) -> None:
        self._scope.set_base_delay(value, only_increase=False)

    @property
    def randomize_delay(self) -> bool:
        return bool(getattr(self._scope, "_jitter", None))

    @property
    def concurrency(self) -> int:
        warnings.warn(
            "Slot.concurrency is deprecated. Per-slot concurrency limits are "
            "now managed by the throttling system.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return getattr(self._scope, "_concurrency", None) or 0

    def free_transfer_slots(self) -> int:
        concurrency = getattr(self._scope, "_concurrency", None) or 0
        return concurrency - len(self.transferring)

    def download_delay(self) -> float:
        delay = self.delay
        if self.randomize_delay:
            return random.uniform(0.5 * delay, 1.5 * delay)  # noqa: S311
        return delay

    def close(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"_DeprecatedSlotView({self._key!r})"


class _DeprecatedSlotsView(Mapping[str, _DeprecatedSlotView]):
    """Deprecated mapping view of active downloads, keyed by slot name."""

    __slots__ = ("_downloader", "_throttler")

    def __init__(self, downloader: Downloader, throttler: ThrottlerProtocol) -> None:
        self._downloader = downloader
        self._throttler = throttler

    def _active_keys(self) -> set[str]:
        return {
            r.meta[Downloader.DOWNLOAD_SLOT]
            for r in self._downloader.active
            if Downloader.DOWNLOAD_SLOT in r.meta
        }

    def __getitem__(self, key: str) -> _DeprecatedSlotView:
        if key not in self._active_keys():
            raise KeyError(key)
        scope = self._throttler.get_scope_manager(key)
        return _DeprecatedSlotView(self._downloader, key, scope)

    def __iter__(self) -> Iterator[str]:
        return iter(self._active_keys())

    def __len__(self) -> int:
        return len(self._active_keys())

    def __contains__(self, key: object) -> bool:
        return key in self._active_keys()


class Downloader:
    DOWNLOAD_SLOT = "download_slot"

    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler
        self.settings: BaseSettings = crawler.settings
        self.signals: SignalManager = crawler.signals
        self.active: set[Request] = set()
        self._transferring: set[Request] = set()
        self.handlers: DownloadHandlers = DownloadHandlers(crawler)
        self.total_concurrency: int = self.settings.getint("CONCURRENT_REQUESTS")
        self.middleware: DownloaderMiddlewareManager = (
            DownloaderMiddlewareManager.from_crawler(crawler)
        )
        self.per_slot_settings: dict[str, dict[str, Any]] = self.settings.getdict(
            "DOWNLOAD_SLOTS"
        )
        if self.per_slot_settings:
            warnings.warn(
                "The DOWNLOAD_SLOTS setting is deprecated. Use THROTTLING_SCOPES for "
                "per-domain configuration instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
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
        return len(self.active) >= self.total_concurrency

    @property
    def domain_concurrency(self) -> int:
        warnings.warn(
            "Downloader.domain_concurrency is deprecated. Per-domain concurrency "
            "limits are now managed by the throttling system.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self.settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN")

    @property
    def randomize_delay(self) -> bool:
        warnings.warn(
            "Downloader.randomize_delay is deprecated. Delay randomization is now "
            "managed by the throttling system.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self.settings.getbool("RANDOMIZE_DOWNLOAD_DELAY")

    @property
    def slots(self) -> _DeprecatedSlotsView:
        warnings.warn(
            "Downloader.slots is deprecated. Use the throttler API instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        assert self.crawler.throttler is not None
        return _DeprecatedSlotsView(self, self.crawler.throttler)

    def _get_slot_key(self, request: Request) -> str:
        assert self.crawler.throttler is not None
        return self.crawler.throttler.get_scopes_key(request)

    def get_slot_key(self, request: Request) -> str:
        warnings.warn(
            "Downloader.get_slot_key() is deprecated. Use "
            "crawler.throttler.get_scopes_key() for the run-time key, or "
            "urlparse_cached(request).hostname if you only need the request "
            "domain.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        # Mirrors the historical keying (an explicit download_slot wins, else
        # the domain); the slot key used at run time comes from the throttler
        # (see _get_slot_key()).
        meta_slot: str | None = request.meta.get(self.DOWNLOAD_SLOT)
        if meta_slot is not None:
            return meta_slot
        return urlparse_cached(request).hostname or ""

    async def _enqueue_request(self, request: Request) -> Response:
        key = self._get_slot_key(request)
        request.meta[self.DOWNLOAD_SLOT] = key
        self.signals.send_catch_log(
            signal=signals.request_reached_downloader,
            request=request,
            spider=self.crawler.spider,
        )
        return await self._download(request)

    async def _download(self, request: Request) -> Response:
        self._transferring.add(request)
        try:
            response: Response = await self.handlers.download_request_async(request)
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
            self._transferring.discard(request)
            self.signals.send_catch_log(
                signal=signals.request_left_downloader,
                request=request,
                spider=self.crawler.spider,
            )

    def close(self) -> None:
        pass
