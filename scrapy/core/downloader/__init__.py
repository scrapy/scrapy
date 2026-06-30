from __future__ import annotations

import random
import warnings
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import inlineCallbacks

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.resolver import dnscache
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
    from scrapy.throttling import ThrottlingScopeManagerProtocol


@dataclass(slots=True, eq=False)
class _Slot:
    """Downloader slot"""

    active: set[Request] = field(default_factory=set, init=False, repr=False)
    transferring: set[Request] = field(default_factory=set, init=False, repr=False)
    lastseen: float = field(default=0, init=False, repr=False)


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
        scope: ThrottlingScopeManagerProtocol | None,
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

    @property
    def lastseen(self) -> float:
        return 0.0

    @property
    def delay(self) -> float:
        if self._scope is not None:
            return self._scope.get_delay()
        return 0.0

    @delay.setter
    def delay(self, value: float) -> None:
        if self._scope is not None:
            self._scope.set_base_delay(value, only_increase=False)

    @property
    def randomize_delay(self) -> bool:
        if self._scope is not None:
            return bool(self._scope.get_jitter())
        return False

    @property
    def concurrency(self) -> int:
        warnings.warn(
            "Slot.concurrency is deprecated. Per-slot concurrency limits are "
            "now managed by the throttling system.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        if self._scope is not None:
            return self._scope.get_concurrency() or 0
        return 0

    def free_transfer_slots(self) -> int:
        concurrency = (
            self._scope.get_concurrency() or 0 if self._scope is not None else 0
        )
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

    def __str__(self) -> str:
        return f"_DeprecatedSlotView({self._key!r})"


class _DeprecatedSlotsView(Mapping[str, _DeprecatedSlotView]):
    """Deprecated mapping view of active downloads, keyed by slot name."""

    __slots__ = ("_downloader", "_throttler")

    def __init__(self, downloader: Downloader, throttler: Any) -> None:
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
        scope = (
            self._throttler.get_scope_manager(key)
            if self._throttler is not None
            else None
        )
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
        self.ip_concurrency: int = self.settings.getint("CONCURRENT_REQUESTS_PER_IP")
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
            for slot_settings in self.per_slot_settings.values():
                for deprecated_key in ("concurrency", "delay", "randomize_delay"):
                    if deprecated_key in slot_settings:
                        warnings.warn(
                            f"The '{deprecated_key}' key in DOWNLOAD_SLOTS is deprecated."
                            " Use THROTTLING_SCOPES to configure per-domain settings"
                            " instead.",
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
    def slots(self) -> _DeprecatedSlotsView:
        warnings.warn(
            "Downloader.slots is deprecated. Use the throttling manager API instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return _DeprecatedSlotsView(self, self.crawler.throttler)

    @_warn_spider_arg
    def _get_slot(
        self, request: Request, spider: Spider | None = None
    ) -> tuple[str, _DeprecatedSlotView]:
        key = self._get_slot_key(request)
        scope = (
            self.crawler.throttler.get_scope_manager(key)
            if self.crawler.throttler is not None
            else None
        )
        return key, _DeprecatedSlotView(self, key, scope)

    def _get_slot_key(self, request: Request) -> str:
        throttler = self.crawler.throttler
        if throttler is not None:
            return throttler.get_slot_key(request)
        return self.get_slot_key(request)

    def get_slot_key(self, request: Request) -> str:
        key = urlparse_cached(request).netloc or ""
        if self.ip_concurrency:
            key = dnscache.get(key, key)
        return key

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
