from __future__ import annotations

import random
import warnings
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import Deferred, inlineCallbacks

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.throttler import _STAMPED_SLOT_META_KEY
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _defer_sleep_async,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from collections.abc import Generator

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
            for r in self._downloader._in_download_handler
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
        # Requests a download handler is working on; the rest of self.active is
        # in the downloader middlewares instead (see
        # _in_downloader_middlewares()).
        self._in_download_handler: set[Request] = set()
        self._download_handler_waiters: list[Deferred[None]] = []
        # Requests waiting for a download handler (see
        # _await_download_handler()). They are not in one yet, but they are not
        # in the downloader middlewares either (see
        # _in_downloader_middlewares()): they are past their middlewares and
        # waiting on nothing but the network.
        self._awaiting_download_handler: set[Request] = set()
        self._downloader_middlewares_waiters: list[Deferred[None]] = []
        self._closed: bool = False
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
        self._fire_downloader_middlewares_waiters()
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
        """Return whether the :setting:`CONCURRENT_REQUESTS` limit is reached.
        A limit of ``0`` means no limit, so nothing is ever held back."""
        return 0 < self.total_concurrency <= len(self.active)

    def _in_downloader_middlewares(self, request: Request) -> bool:
        """Return whether the downloader middlewares are processing *request*,
        i.e. it is in the downloader but neither in a download handler nor
        waiting for one (see :meth:`_await_download_handler`).

        Such a request is not using the network, even though it may be holding a
        :ref:`throttling <throttling>` concurrency slot, and it may be waiting
        for another request that a downloader middleware is downloading. That is
        what makes its slot safe to lend (see
        :meth:`~scrapy.throttler.Throttler._can_lend_slot`).

        A request waiting for a download handler is not using the network
        either, but it is past its middlewares, so it waits on nothing but the
        network and will reach a handler on its own. Lending its slot would
        break no deadlock, and it is the one request whose progress the loan
        would then be holding back.
        """
        return (
            request in self.active
            and request not in self._in_download_handler
            and request not in self._awaiting_download_handler
        )

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
        # Record that this value is ours, so that a request that inherits it
        # (e.g. a redirect or a retry, which copy meta) resolves its own
        # throttling scopes instead of reusing it, and is not reported as using
        # the deprecated download_slot meta key; see
        # Throttler._resolve_scopes_sync. Only a value of ours is stamped: an
        # inherited one is ours if it matches the stamp that came with it, and
        # anything else is a user's choice of scope, which must survive into the
        # requests derived from this one.
        previous: str | None = request.meta.get(self.DOWNLOAD_SLOT)
        if previous is None or previous == request.meta.get(_STAMPED_SLOT_META_KEY):
            request.meta[_STAMPED_SLOT_META_KEY] = key
        request.meta[self.DOWNLOAD_SLOT] = key
        self.signals.send_catch_log(
            signal=signals.request_reached_downloader,
            request=request,
            spider=self.crawler.spider,
        )
        return await self._download(request)

    async def _acquire_download_handler_slot(self) -> None:
        """Wait until fewer than :setting:`CONCURRENT_REQUESTS` requests are in a
        download handler.

        Requests coming from the scheduler are kept under that limit by the
        engine, which stops dequeuing them (see
        :meth:`~scrapy.core.engine.ExecutionEngine.needs_backout`), but
        requests sent outside the scheduling cycle
        never went through the scheduler, so this is what limits them.

        A download handler slot is only held while a download handler is working
        on a request, and such a request completes on its own. So a request that
        a downloader middleware sends as a prerequisite of another one (as the
        built-in robots.txt middleware does) cannot be held back by that other
        one, which holds no such slot while its middlewares run.

        That reasoning does not extend to a request sent from *within* a download
        handler, which does hold a slot while it waits: with every slot taken by
        such requests, none of them could ever get one. Download handlers must
        not send requests through :meth:`crawler.engine.download_async()
        <scrapy.core.engine.ExecutionEngine.download_async>`.
        """
        while self._download_handler_slots_full():
            # Register the waiter before giving up control, or a request leaving
            # a download handler in between would go unnoticed.
            waiter: Deferred[None] = Deferred()
            self._download_handler_waiters.append(waiter)
            await maybe_deferred_to_future(waiter)

    def _download_handler_slots_full(self) -> bool:
        """Return whether every download handler slot is taken. A closed
        downloader never holds anything back, since no request will ever leave a
        download handler again."""
        if self._closed:
            return False
        return 0 < self.total_concurrency <= len(self._in_download_handler)

    async def _await_download_handler(self, request: Request) -> None:
        """Wait until *request* may be handed to a download handler: until a
        download handler slot is free (see
        :meth:`_acquire_download_handler_slot`) and until the throttling scopes
        of *request* have room for it there (see
        :meth:`~scrapy.throttler.ThrottlerProtocol.download_handler_blocked`).

        Both are rechecked after every wait, since waiting on one can close the
        other, and this returns without giving up control once they are both
        open, so that the caller can hand the request over against exactly the
        state that was checked.
        """
        # Tracked for the whole wait, so that a request waiting at either gate
        # does not read as being in the downloader middlewares and get its
        # concurrency slot lent away; see _in_downloader_middlewares().
        self._awaiting_download_handler.add(request)
        try:
            while True:
                await self._acquire_download_handler_slot()
                if self._closed or not self._download_handler_blocked(request):
                    return
                await self._wait_for_download_handler_exit()
        finally:
            self._awaiting_download_handler.discard(request)

    def _download_handler_blocked(self, request: Request) -> bool:
        throttler = self.crawler.throttler
        return throttler is not None and throttler.download_handler_blocked(request)

    async def _wait_for_download_handler_exit(self) -> None:
        """Wait for a request to leave a download handler, which is what frees
        room on the network for a scope (as does :meth:`close`, after which
        nothing is held back).

        A request is only ever held out of a download handler by requests that
        are in one, and those end on their own, so this cannot wait forever.
        """
        waiter: Deferred[None] = Deferred()
        self._download_handler_waiters.append(waiter)
        await maybe_deferred_to_future(waiter)

    def _downloader_middlewares_event(self) -> Deferred[None]:
        """Return a :class:`~twisted.internet.defer.Deferred` that fires the next
        time a request reaches the downloader middlewares (see
        :meth:`_in_downloader_middlewares`), i.e. when one enters the downloader
        or leaves a download handler, as well as on :meth:`close`.

        Such a request holds a :ref:`throttling <throttling>` concurrency slot
        that it is not using, which the throttler may then lend to a request sent
        from a downloader middleware; see
        :meth:`~scrapy.throttler.ThrottlerProtocol.acquire`.
        """
        event: Deferred[None] = Deferred()
        self._downloader_middlewares_waiters.append(event)
        return event

    def _discard_downloader_middlewares_event(self, event: Deferred[None]) -> None:
        """Drop a pending *event* returned by
        :meth:`_downloader_middlewares_event`, for a wait that ended for a
        different reason."""
        with suppress(ValueError):
            self._downloader_middlewares_waiters.remove(event)

    def _leave_download_handler(self, request: Request) -> None:
        """Record that no download handler is working on *request* anymore.

        That frees a download handler slot, and it puts *request* back in the
        downloader middlewares for as long as they process its outcome.

        Calling it more than once for the same request is a no-op, so the error
        path of :meth:`_download` can release the handler early without the
        ``finally`` block firing every waiter a second time.
        """
        if request not in self._in_download_handler:
            return
        self._in_download_handler.discard(request)
        self._fire_download_handler_waiters()
        self._fire_downloader_middlewares_waiters()

    def _fire_download_handler_waiters(self) -> None:
        waiters = self._download_handler_waiters
        self._download_handler_waiters = []
        for waiter in waiters:
            if not waiter.called:
                waiter.callback(None)

    def _fire_downloader_middlewares_waiters(self) -> None:
        waiters = self._downloader_middlewares_waiters
        self._downloader_middlewares_waiters = []
        for waiter in waiters:
            if not waiter.called:
                waiter.callback(None)

    async def _download(self, request: Request) -> Response:
        await self._await_download_handler(request)
        self._in_download_handler.add(request)
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
            # The handler is done with the request, so free its slot before
            # giving up control below rather than a reactor turn later.
            self._leave_download_handler(request)
            await _defer_sleep_async()
            raise
        finally:
            self._leave_download_handler(request)
            self.signals.send_catch_log(
                signal=signals.request_left_downloader,
                request=request,
                spider=self.crawler.spider,
            )

    def close(self) -> None:
        # Release anything waiting for a request to leave a download handler or
        # to reach the downloader middlewares, since neither will happen again.
        self._closed = True
        self._fire_download_handler_waiters()
        self._fire_downloader_middlewares_waiters()
