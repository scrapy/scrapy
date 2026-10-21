from __future__ import annotations

import warnings
from dataclasses import dataclass
from logging import getLogger
from time import perf_counter
from typing import TYPE_CHECKING, Any

from formerly import deprecated_class
from twisted.internet.defer import Deferred, DeferredList, inlineCallbacks

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import DownloadCancelledError, ScrapyDeprecationWarning
from scrapy.throttler import (
    _STAMPED_SLOT_META_KEY,
    ThrottlingScopeManager,
    _default_jitter,
)
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _Event,
    _process_pending_io,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings
    from scrapy.signalmanager import SignalManager
    from scrapy.throttler import ThrottlerProtocol

logger = getLogger(__name__)


@dataclass(slots=True, eq=False)
class _Slot:
    """Downloader slot.

    Nothing uses it anymore: it only gives the deprecated :class:`Slot` alias a
    base, so that code that still builds one keeps working.
    """

    concurrency: int
    delay: float
    jitter: float

    # Hand-written to also accept randomize_delay, a boolean alternative to
    # jitter.
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
        self.concurrency = concurrency
        self.delay = delay
        self.jitter = jitter if jitter is not None else 0.5 * bool(randomize_delay)

    @property
    def randomize_delay(self) -> bool:
        return bool(self.jitter)

    @randomize_delay.setter
    def randomize_delay(self, value: bool) -> None:
        self.jitter = 0.5 if value else 0.0


Slot = deprecated_class(
    "Slot",
    _Slot,
    category=ScrapyDeprecationWarning,
    old_path="scrapy.core.downloader.Slot",
    subclass_message="{cls} inherits from the deprecated Slot class.",
    instance_message="The Slot class is deprecated.",
)


class _DeprecatedSlotView:
    """Deprecated per-domain slot view backed by the downloader and throttler."""

    __slots__ = ("_downloader", "_key", "_throttler")

    def __init__(
        self,
        downloader: Downloader,
        key: str,
        throttler: ThrottlerProtocol,
    ) -> None:
        self._downloader = downloader
        self._key = key
        self._throttler = throttler

    @property
    def _scope(self) -> ThrottlingScopeManager:
        return self._throttler.get_scope_manager(self._key)

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

    @property
    def lastseen(self) -> float:
        return self._scope._last_seen or 0.0

    @property
    def delay(self) -> float:
        return self._scope.get_base_delay()

    @delay.setter
    def delay(self, value: float) -> None:
        self._scope.set_base_delay(value, only_increase=False)

    @property
    def jitter(self) -> float:
        return self._scope._jitter

    @property
    def randomize_delay(self) -> bool:
        return bool(self.jitter)

    @property
    def concurrency(self) -> int:
        return self._scope.get_concurrency()

    def free_transfer_slots(self) -> int:
        return self._scope.get_concurrency() - len(self.transferring)

    def download_delay(self) -> float:
        return ThrottlingScopeManager._apply_jitter(self.delay, self.jitter)

    def close(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"_DeprecatedSlotView({self._key!r})"


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
        # Fires when a request leaves a download handler, i.e. when it frees a
        # download handler slot and room on the network for its scopes.
        self._download_handler_exit = _Event()
        # Requests waiting for a download handler (see
        # _await_download_handler()). They are not in one yet, but they are not
        # in the downloader middlewares either (see
        # _in_downloader_middlewares()): they are past their middlewares and
        # waiting on nothing but the network.
        self._awaiting_download_handler: set[Request] = set()
        self._downloader_middlewares_entry = _Event()
        self._closed: bool = False
        self.handlers: DownloadHandlers = DownloadHandlers(crawler)
        self.total_concurrency: int = self.settings.getint("CONCURRENT_REQUESTS")
        self.middleware: DownloaderMiddlewareManager = build_from_crawler(
            DownloaderMiddlewareManager, crawler
        )
        self._accepting_requests: bool = True
        self._download_tasks: dict[Request, Deferred[Response]] = {}
        self._per_slot_settings: dict[str, dict[str, Any]] = self.settings.getdict(
            "DOWNLOAD_SLOTS"
        )
        if self._per_slot_settings:
            warnings.warn(
                "The DOWNLOAD_SLOTS setting is deprecated. Use THROTTLING_SCOPES for "
                "per-domain configuration instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        self._stats = crawler.stats
        # (reason, start_time): current backout reason and when it began, or
        # (None, None) if not backing out.
        self._last_backout: tuple[str | None, float | None] = (None, None)
        self._max_active_size_warned = False

    @property
    def per_slot_settings(self) -> dict[str, dict[str, Any]]:
        self._warn_per_slot_settings()
        return self._per_slot_settings

    @per_slot_settings.setter
    def per_slot_settings(self, value: dict[str, dict[str, Any]]) -> None:
        self._warn_per_slot_settings()
        self._per_slot_settings = value

    @staticmethod
    def _warn_per_slot_settings() -> None:
        warnings.warn(
            "Downloader.per_slot_settings is deprecated, and Scrapy no longer "
            "uses it. Use THROTTLING_SCOPES for per-domain configuration "
            "instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=3,
        )

    @inlineCallbacks
    @_warn_spider_arg
    def fetch(
        self, request: Request, spider: Spider | None = None
    ) -> Generator[Deferred[Any], Any, Response | Request]:
        self.active.add(request)
        self._downloader_middlewares_entry.fire()
        self.middleware._count_rough_size(request)
        try:
            result: Response | Request = yield (
                deferred_from_coro(
                    self.middleware.download_async(self._enqueue_request, request)
                )
            )
            return result
        finally:
            self.active.remove(request)
            self.middleware._discount_rough_size(request)

    def _record_backout(self, reason: str | None) -> None:
        last_reason, last_reason_start_time = self._last_backout
        if last_reason == reason:
            return
        current_time = perf_counter()
        if last_reason is not None and self._stats is not None:
            assert last_reason_start_time is not None
            last_reason_seconds = current_time - last_reason_start_time
            self._stats.inc_value("request_backout_seconds/total", last_reason_seconds)
            self._stats.inc_value(
                f"request_backout_seconds/{last_reason}", last_reason_seconds
            )
        self._last_backout = (reason, current_time)

    def needs_backout(self) -> bool:
        # A total concurrency of 0 means no limit.
        if 0 < self.total_concurrency <= len(self.active):
            self._record_backout("concurrency")
            return True
        if self._exceeds_max_active_size():
            self._record_backout("response_max_active_size")
            if not self._max_active_size_warned:
                self._max_active_size_warned = True
                logger.info(
                    f"Pausing request processing: the active response size "
                    f"({self.middleware._total_active_size} B) has reached "
                    f"RESPONSE_MAX_ACTIVE_SIZE "
                    f"({self.middleware._max_active_size} B). See "
                    f"https://docs.scrapy.org/en/latest/topics/settings.html#response-max-active-size "
                    f"and the request_backout_seconds/response_max_active_size "
                    f"stat. This message is only logged once."
                )
            return True
        self._record_backout(None)
        return False

    def _exceeds_max_active_size(self) -> bool:
        max_active_size = self.middleware._max_active_size
        return (
            bool(max_active_size)
            and self.middleware._total_active_size >= max_active_size
        )

    def _in_downloader_middlewares(self, request: Request) -> bool:
        """Return whether the downloader middlewares are processing *request*,
        i.e. it is in the downloader but neither in a download handler nor
        waiting for one (see :meth:`_await_download_handler`).

        Such a request may be holding a :ref:`throttling <throttling>`
        concurrency slot while waiting for another request that a downloader
        middleware is downloading, which is what makes its slot safe to lend
        (see :meth:`~scrapy.throttler.Throttler._can_lend_slot`). A request
        waiting for a download handler is excluded: it waits on nothing but the
        network, so lending its slot would break no deadlock and would only hold
        it back.
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
        return bool(_default_jitter(self.settings))

    @property
    def slots(self) -> dict[str, _DeprecatedSlotView]:
        warnings.warn(
            "Downloader.slots is deprecated. Use the throttler API instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        throttler = self.crawler.throttler
        return {
            key: _DeprecatedSlotView(self, key, throttler)
            for key in {
                request.meta[self.DOWNLOAD_SLOT]
                for request in self.active
                if self.DOWNLOAD_SLOT in request.meta
            }
        }

    def _get_slot_key(self, request: Request) -> str:
        return self.crawler.throttler.get_scopes_key(request)

    def get_slot_key(self, request: Request) -> str:
        warnings.warn(
            "Downloader.get_slot_key() is deprecated. Use "
            "crawler.throttler.get_applied_scopes() for the throttling scopes of "
            "a request, or urlparse_cached(request).hostname if you only need "
            "the request domain.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        # An explicit download_slot wins, else the domain. The key used at run
        # time comes from the throttler (see _get_slot_key()).
        meta_slot: str | None = request.meta.get(self.DOWNLOAD_SLOT)
        if meta_slot is not None:
            return meta_slot
        return urlparse_cached(request).hostname or ""

    async def _enqueue_request(self, request: Request) -> Response:
        if not self._accepting_requests:
            raise DownloadCancelledError(
                "The downloader is shutting down and not accepting new requests"
            )
        key = self._get_slot_key(request)
        # Stamp the value as ours, so that a request that inherits it (a
        # redirect, a retry) resolves its own throttling scopes instead of
        # reusing it, and is not reported as using the deprecated download_slot
        # meta key; see Throttler._resolve_scopes_sync. An inherited value is
        # ours if it matches the stamp that came with it; anything else is a
        # user's choice of scope, which must survive into derived requests.
        previous: str | None = request.meta.get(self.DOWNLOAD_SLOT)
        if previous is None or previous == request.meta.get(_STAMPED_SLOT_META_KEY):
            request.meta[_STAMPED_SLOT_META_KEY] = key
        request.meta[self.DOWNLOAD_SLOT] = key
        self.signals.send_catch_log(
            signal=signals.request_reached_downloader,
            request=request,
            spider=self.crawler.spider,
        )
        # A task of its own, so that stop() can cancel it.
        download_dfd = deferred_from_coro(self._download(request))
        self._download_tasks[request] = download_dfd
        try:
            return await maybe_deferred_to_future(download_dfd)
        finally:
            del self._download_tasks[request]

    def _download_handler_slots_full(self) -> bool:
        """Return whether every download handler slot
        (:setting:`CONCURRENT_REQUESTS`) is taken. A closed downloader never
        holds anything back, since no request will ever leave a download handler
        again.

        The engine keeps scheduled requests under that limit by not dequeuing
        them (see :meth:`~scrapy.core.engine.ExecutionEngine.needs_backout`);
        this is what limits requests sent through
        :meth:`crawler.engine.download_async()
        <scrapy.core.engine.ExecutionEngine.download_async>` instead.
        """
        if self._closed:
            return False
        return 0 < self.total_concurrency <= len(self._in_download_handler)

    async def _await_download_handler(self, request: Request) -> None:
        """Wait until *request* may be handed to a download handler: until a
        download handler slot is free (see
        :meth:`_download_handler_slots_full`) and until the throttling scopes of
        *request* have room for it there (see
        :meth:`~scrapy.throttler.ThrottlerProtocol.download_handler_blocked`).

        Both are rechecked after every wait, since waiting on one can close the
        other, and this returns without giving up control once they are both
        open, so that the caller hands the request over against exactly the
        state that was checked.

        A slot is only held while a download handler works on a request, and
        such a request completes on its own, so a prerequisite sent from a
        downloader middleware cannot be held back by the request waiting for it.
        That does not hold for a request sent from *within* a download handler,
        which keeps its slot while it waits: download handlers must not use
        ``download_async()``.
        """
        # Tracked for the whole wait so that the request does not read as being
        # in the downloader middlewares and get its slot lent away; see
        # _in_downloader_middlewares().
        self._awaiting_download_handler.add(request)
        try:
            while self._download_handler_slots_full() or (
                not self._closed and self._download_handler_blocked(request)
            ):
                await self._wait_for_download_handler_exit()
        finally:
            self._awaiting_download_handler.discard(request)

    def _download_handler_blocked(self, request: Request) -> bool:
        return self.crawler.throttler.download_handler_blocked(request)

    async def _wait_for_download_handler_exit(self) -> None:
        """Wait for a request to leave a download handler, which is what frees
        room on the network for a scope (as does :meth:`close`, after which
        nothing is held back).

        A request is only ever held out of a download handler by requests that
        are in one, and those end on their own, so this cannot wait forever.
        """
        await maybe_deferred_to_future(self._download_handler_exit.wait())

    def _downloader_middlewares_event(self) -> Deferred[None]:
        """Return a :class:`~twisted.internet.defer.Deferred` that fires the next
        time a request reaches the downloader middlewares (see
        :meth:`_in_downloader_middlewares`), i.e. when one enters the downloader
        or leaves a download handler, as well as on :meth:`close`. That is when
        a slot the throttler may lend out appears; see
        :meth:`~scrapy.throttler.ThrottlerProtocol.acquire`.

        Firing on arrival too covers the window between a request reserving its
        slot and reaching the downloader: a holder in that window reads as being
        in neither place, so a prerequisite looking for a slot to borrow finds
        none, and nothing else would tell it to look again.
        """
        return self._downloader_middlewares_entry.wait()

    def _discard_downloader_middlewares_event(self, event: Deferred[None]) -> None:
        """Drop a pending *event* returned by
        :meth:`_downloader_middlewares_event`, for a wait that ended for a
        different reason."""
        self._downloader_middlewares_entry.discard(event)

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
        self._download_handler_exit.fire()
        self._downloader_middlewares_entry.fire()

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
            await _process_pending_io()
            raise
        finally:
            self._leave_download_handler(request)
            self.signals.send_catch_log(
                signal=signals.request_left_downloader,
                request=request,
                spider=self.crawler.spider,
            )

    async def stop(self) -> int:
        self._accepting_requests = False
        cancelled_dfds = [
            download_dfd
            for download_dfd in self._download_tasks.values()
            if not download_dfd.called
        ]
        for download_dfd in cancelled_dfds:
            download_dfd.cancel()
        if cancelled_dfds:
            # Wait for the cancellations themselves to settle instead of
            # guessing how many event loop iterations that takes.
            await maybe_deferred_to_future(
                DeferredList(cancelled_dfds, consumeErrors=True)
            )
        return len(cancelled_dfds)

    def close(self) -> None:
        self._accepting_requests = False
        # Release anything waiting for a request to leave a download handler or
        # to reach the downloader middlewares, since neither will happen again.
        self._closed = True
        self._download_handler_exit.fire()
        self._downloader_middlewares_entry.fire()
        self._record_backout(None)

    async def _close_async(self) -> None:
        """Close the downloader and its download handlers."""
        self.close()
        await self.handlers._close()
