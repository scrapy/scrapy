from __future__ import annotations

import contextlib
import logging
import random
import time
import warnings
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from functools import wraps
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, TypeVar, cast
from weakref import WeakKeyDictionary

from twisted.internet.defer import Deferred
from typing_extensions import Self

from scrapy import signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import SETTINGS_PRIORITIES
from scrapy.utils.asyncio import sleep, wait_for_first
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.http import Request
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


class BackoffConfig(TypedDict, total=False):
    """Per-scope override of the backoff settings.

    Used as the value of the ``"backoff"`` key of :class:`ThrottlingScopeConfig`
    entries. Any key left out falls back to the corresponding global
    ``BACKOFF_*`` setting.
    """

    http_codes: list[int]
    exceptions: list[str]
    delay_factor: float
    max_delay: float
    min_delay: float
    jitter: float | list[float]


class RampupConfig(TypedDict, total=False):
    """Per-scope override of the rampup settings.

    Used as the value of the ``"rampup"`` key of :class:`ThrottlingScopeConfig`
    entries when fine-tuning rampup beyond a plain ``True``. Any key left out
    falls back to its default (or, for ``backoff_target``, to
    :setting:`RAMPUP_BACKOFF_TARGET`).
    """

    backoff_target: float
    delay_factor: float
    min_delay: float


class ThrottlingScopeConfig(TypedDict, total=False):
    """Accepted keys of :setting:`THROTTLING_SCOPES` entries.

    Every key is optional; missing keys fall back to the matching global
    setting (e.g. ``delay`` falls back to :setting:`DOWNLOAD_DELAY`).
    """

    concurrency: int

    delay: float

    jitter: float | list[float]
    """Magnitude of the random variation applied to ``delay``; the per-scope
    override of :setting:`RANDOMIZE_DOWNLOAD_DELAY` (``0`` disables it, ``0.5``
    means ±50%)."""

    quota: float
    window: float
    rampup: bool | RampupConfig

    manager: str | type
    """Import path or class of a custom :setting:`THROTTLING_SCOPE_MANAGER` for
    this scope."""

    backoff: BackoffConfig

    ignore_robots_txt: bool
    """Silence the warning logged when this configuration is more aggressive
    than a robots.txt ``Crawl-delay``."""


ScopeID = str
RequestScopes = None | ScopeID | Iterable[ScopeID] | dict[ScopeID, float | None]


def iter_scopes(scopes: RequestScopes) -> Iterable[ScopeID]:
    """Iterate over the scope IDs of *scopes*, whatever its form.

    :class:`~ThrottlingManagerProtocol.get_scopes` (and
    :meth:`~ThrottlingManagerProtocol.get_resolved_scopes`) may return a single
    scope ID, an iterable of them, a ``{scope_id: quota}`` mapping, or ``None``;
    this helper normalizes any of those into an iterable of scope IDs, e.g. to
    react to a request's scopes in a custom middleware.
    """
    return (scope for scope, _ in iter_scope_values(scopes))


def iter_scope_values(scopes: RequestScopes) -> Iterable[tuple[ScopeID, float | None]]:
    """Iterate over *scopes* as ``(scope_id, value)`` pairs.

    For dict scopes the value is the expected :ref:`throttling quota
    <throttling-quotas>` consumption; for every other form the value is
    ``None``.
    """
    if scopes is None:
        return
    if isinstance(scopes, str):
        yield scopes, None
        return
    if isinstance(scopes, dict):
        yield from scopes.items()
        return
    for scope in scopes:
        yield scope, None


def _load_exceptions(exceptions: Iterable[Any]) -> tuple[type[BaseException], ...]:
    """Resolve *exceptions* (exception classes or their import paths) to a tuple
    of exception classes."""
    return tuple(
        load_object(exc) if isinstance(exc, str) else exc for exc in exceptions
    )


def _effective_priority(settings: BaseSettings, name: str) -> int:
    """Return the priority of setting *name*, treating an unset setting (no
    priority, ``None``) as just below ``"default"`` so it never wins over one
    that is at least at its default value."""
    priority = settings.getpriority(name)
    return SETTINGS_PRIORITIES["default"] - 1 if priority is None else priority


def _default_scope_concurrency(settings: BaseSettings) -> int:
    """Return the default concurrency of a throttling scope that does not set
    its own ``concurrency``.

    This is :setting:`THROTTLING_SCOPE_CONCURRENCY`, except that the deprecated
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` setting is bridged in when set at a
    higher :ref:`priority <populating-settings>`. When neither is set
    explicitly, the historical :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` value is
    kept for backward compatibility (its default flips to
    :setting:`THROTTLING_SCOPE_CONCURRENCY` in a future version; see
    :func:`_warn_on_deprecated_concurrency`).
    """
    default_priority = SETTINGS_PRIORITIES["default"]
    domain_priority = _effective_priority(settings, "CONCURRENT_REQUESTS_PER_DOMAIN")
    scope_priority = _effective_priority(settings, "THROTTLING_SCOPE_CONCURRENCY")
    if domain_priority > scope_priority:
        return settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN")
    if scope_priority > domain_priority:
        return settings.getint("THROTTLING_SCOPE_CONCURRENCY")
    # Equal priority: on an explicit (higher-than-default) tie the new setting
    # wins; when neither is set (both at "default") keep the historical
    # per-domain value so existing behavior is preserved.
    if domain_priority <= default_priority:
        return settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN")
    return settings.getint("THROTTLING_SCOPE_CONCURRENCY")


def _warn_on_deprecated_concurrency(settings: BaseSettings) -> None:
    """Warn about the concurrency settings bridged by
    :func:`_default_scope_concurrency`. Call once per crawl (see
    :meth:`ThrottlingManager.__init__`).

    When :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` is set explicitly, warn that
    it is deprecated. When neither concurrency setting is set explicitly, warn
    that the effective per-scope concurrency is still the deprecated setting's
    value (kept for backward compatibility) and will drop to
    :setting:`THROTTLING_SCOPE_CONCURRENCY`'s default once the deprecated
    setting is removed, so users can pin it explicitly."""
    default_priority = SETTINGS_PRIORITIES["default"]
    domain_set = (
        _effective_priority(settings, "CONCURRENT_REQUESTS_PER_DOMAIN")
        > default_priority
    )
    scope_set = (
        _effective_priority(settings, "THROTTLING_SCOPE_CONCURRENCY") > default_priority
    )
    if domain_set:
        warnings.warn(
            "The CONCURRENT_REQUESTS_PER_DOMAIN setting is deprecated, use "
            "THROTTLING_SCOPE_CONCURRENCY instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
    elif not scope_set:
        # This warn-then-flip message only makes sense while the two defaults
        # differ (otherwise it reads "will drop from 1 to 1"). That invariant is
        # guarded by test_deprecated_concurrency_defaults_differ rather than at
        # run time, so a crawl is never aborted over it.
        current = settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN")
        future = settings.getint("THROTTLING_SCOPE_CONCURRENCY")
        warnings.warn(
            f"The effective per-scope (per-domain) concurrency is {current}, "
            f"the default of the deprecated CONCURRENT_REQUESTS_PER_DOMAIN "
            f"setting, which is still respected for backward compatibility. "
            f"Once CONCURRENT_REQUESTS_PER_DOMAIN is removed, it will drop to "
            f"{future}, the default of THROTTLING_SCOPE_CONCURRENCY. Set "
            f"THROTTLING_SCOPE_CONCURRENCY explicitly to choose a value and "
            f"silence this warning.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )


def _to_scope_dict(scopes: RequestScopes) -> dict[ScopeID, float | None]:
    """Normalize *scopes* (``None``, a scope id, an iterable of scope ids or a
    ``{scope_id: quota}`` dict) into a ``{scope_id: quota}`` dict, using ``None``
    as the quota of scopes that have none."""
    if isinstance(scopes, dict):
        return scopes
    if scopes is None:
        return {}
    if isinstance(scopes, str):
        return {scopes: None}
    if isinstance(scopes, Iterable):
        return dict.fromkeys(scopes)
    raise TypeError(
        f"Invalid type ({type(scopes)}) of scopes value "
        f"{scopes!r}. Expected None, str, Iterable or dict."
    )


def add_scope(
    scopes: RequestScopes,
    scope: ScopeID,
    value: float | None = None,
    /,
) -> dict[ScopeID, float | None]:
    """Add *scope* to *scopes* with *value*, returning a ``{scope_id: quota}``
    dict.

    This is a utility function to help extending the output of
    :meth:`~ThrottlingManagerProtocol.get_scopes`, e.g. in
    :class:`ThrottlingManager` subclasses.

    Adding a scope with a *value* fails if it is already present, so an existing
    :ref:`quota <throttling-quotas>` is never silently overwritten; adding it
    without a value leaves any existing entry untouched.
    """
    result = _to_scope_dict(scopes)
    if value is None:
        result.setdefault(scope, None)
        return result
    if scope in result:
        raise TypeError(f"Scope {scope!r} already has a value in {scopes!r}")
    result[scope] = value
    return result


class ThrottlingManagerProtocol(Protocol):
    """A protocol for :setting:`THROTTLING_MANAGER` :ref:`components
    <topics-components>`."""

    async def get_scopes(self, request: Request) -> RequestScopes:
        """Return the :ref:`throttling scopes <throttling-scopes>` that apply
        to *request*.

        Return ``None`` if no scopes apply, a string for a single scope, an
        iterable of strings for multiple scopes, or a dict with scope names as
        keys and :ref:`throttling quotas <throttling-quotas>` as values.
        """

    def get_resolved_scopes(self, request: Request) -> RequestScopes:
        """Return the :ref:`throttling scopes <throttling-scopes>` under which
        *request* was (or will be) sent, without re-resolving them.

        This is the synchronous counterpart of :meth:`get_scopes`: it returns
        the scopes resolved earlier (e.g. at enqueue or :meth:`acquire` time)
        and persisted on ``request.meta``, falling back to a best-effort
        synchronous resolution only if none were persisted. Use it, rather than
        :meth:`get_scopes`, to attribute a response or exception to the very
        scopes the request was sent under — e.g. from a downloader middleware or
        a spider callback that wants to :meth:`back_off` based on the response.
        """

    async def acquire(self, request: Request) -> None:
        """Block until *request* is allowed to be sent by all of its scopes.

        This is the throttling gate that the engine awaits before releasing a
        request to the downloader.
        """

    def release(self, request: Request) -> None:
        """Release the concurrency slots that :meth:`acquire` reserved for
        *request*.

        The engine calls this once *request* has finished downloading (whether
        it succeeded, failed or returned a new request), so that scopes that
        enforce a concurrency limit can let other requests through.
        """

    def is_ready(self, request: Request) -> bool:
        """Return whether every scope of *request* allows it to be sent right
        now, i.e. all time-based gates (delay, backoff, quota window) are open
        *and* a concurrency slot is free in every scope.

        This is the synchronous, non-blocking counterpart of :meth:`acquire`,
        used by a :ref:`throttling-aware scheduler
        <throttling-aware-scheduler>` to decide whether a request can be
        dequeued now. It assumes the scopes of *request* have already been
        resolved (e.g. by an earlier :meth:`get_scopes` call at enqueue time).
        """

    def reserve(self, request: Request) -> None:
        """Claim a send for *request*: record the send on every one of its
        scopes and mark *request* as reserved, so that a later :meth:`acquire`
        for it returns immediately without reserving again.

        A :ref:`throttling-aware scheduler <throttling-aware-scheduler>` calls
        this when it decides to dequeue *request* (after :meth:`is_ready`
        returned ``True``). The reservation is released by :meth:`release`.
        """

    def get_time_until_ready(self, request: Request) -> float | None:
        """Return the number of seconds until every time-based gate of
        *request* would be open, or ``None`` if no time-based gate is currently
        blocking it (only a concurrency slot could be).

        Used by a :ref:`throttling-aware scheduler
        <throttling-aware-scheduler>` to schedule a wakeup when all pending
        requests are time-blocked.
        """

    def get_slot_key(self, request: Request) -> str:
        """Return a single string key for *request*, derived from its scopes.

        For a single scope this is the scope ID itself; for multiple scopes
        the sorted scope IDs are joined with ``"+"``.  This is the synchronous
        counterpart of :meth:`get_scopes`, used wherever a plain string key is
        needed (e.g. scheduler priority queues).
        """

    def get_scope_load(self, scope_id: str) -> float:
        """Return the current load of the scope identified by *scope_id*: its
        active sends divided by its concurrency limit (or by the global
        :setting:`CONCURRENT_REQUESTS` when the scope has no explicit limit).

        Used by a :ref:`throttling-aware scheduler
        <throttling-aware-scheduler>` to balance dequeuing across scopes,
        preferring the least-loaded ones.
        """

    def get_request_delay(self, request: Request, now: float | None = None) -> float:
        """Return how many seconds *request* must still be held individually
        because of its :reqmeta:`throttling_delay`, or ``0.0`` if it has none
        or it has already elapsed. The one-time delay is started on the first
        call.

        Unlike a scope delay, this affects only *request*: a
        :ref:`throttling-aware scheduler <throttling-aware-scheduler>` must
        hold the request back on its own, **without** blocking other requests
        that share its scopes.
        """

    def back_off(
        self,
        scopes: RequestScopes,
        *,
        delay: float | None = None,
        cap: bool = True,
    ) -> None:
        """Register a :ref:`backoff <backoff>` trigger for each of *scopes*.

        This is the general-purpose way to make a scope slow down, available to
        any component through :attr:`crawler.throttler
        <scrapy.crawler.Crawler.throttler>`. The built-in :class:`backoff
        middleware <scrapy.downloadermiddlewares.backoff.BackoffMiddleware>`
        calls it for :setting:`BACKOFF_HTTP_CODES` responses and
        :setting:`BACKOFF_EXCEPTIONS` exceptions, but a downloader middleware or
        spider callback can call it too (e.g. to back off based on the response
        body of a specific site).

        *scopes* accepts the same shapes as the output of :meth:`get_scopes`
        (typically the result of :meth:`get_resolved_scopes` for a request).

        An exponential backoff step is always applied to the scope's delay.
        When *delay* is given, the scope is *additionally* held back for at
        least *delay* seconds before its next request: a one-time gate (e.g.
        from a :ref:`Retry-After <retry-after>` header), not a change to the
        steady-state delay. *cap* limits *delay* to :setting:`BACKOFF_MAX_DELAY`;
        set it to ``False`` for trusted, programmatic delays.
        """

    def delay_scope(self, scope_id: str, delay: float) -> None:
        """Hold back the scope identified by *scope_id* for at least *delay*
        seconds before its next request, and register a :ref:`backoff
        <backoff>` trigger for the scope.

        Like a :ref:`Retry-After <retry-after>` response header, this is a
        one-time delay (the scope's steady-state delay grows by one backoff
        step and then recovers), not a permanent one; call it again to keep a
        scope slowed down for longer.

        This is shorthand for :meth:`back_off(scope_id, delay=delay,
        cap=False) <back_off>`. Unlike a ``Retry-After`` header, *delay* is
        **not** capped at :setting:`BACKOFF_MAX_DELAY`: that cap guards against
        untrusted input, whereas a ``delay_scope`` call is trusted.
        """

    def reconcile_quota(
        self,
        scopes: RequestScopes,
        *,
        consumed: float | None = None,
        remaining: float | None = None,
    ) -> None:
        """Reconcile the :ref:`throttling quota <throttling-quotas>` of each of
        *scopes* with an actually *consumed* amount (a delta to add) or a
        *remaining* amount (an absolute value), correcting the estimate used
        when requests were sent.

        Like :meth:`back_off`, this is meant to be called from a downloader
        middleware or spider callback that learns the real quota cost of a
        request from its response.
        """

    def get_scope_delay(self, scope_id: str) -> float:
        """Return the current base (non-backoff) delay of *scope_id*, in seconds."""

    def set_scope_delay(self, scope_id: str, delay: float) -> None:
        """Set the base (non-backoff) delay of *scope_id* to *delay* seconds.

        Unlike :meth:`delay_scope`, this both raises and lowers the delay and is
        not counted as backoff; it lets a component drive the scope delay
        directly (e.g. an adaptive-delay extension).
        """

    def get_scope_manager(self, scope_id: str) -> ThrottlingScopeManagerProtocol:
        """Return the :class:`ThrottlingScopeManagerProtocol` instance handling
        the scope identified by *scope_id*, creating it if necessary."""


_GetScopesMethod = TypeVar(
    "_GetScopesMethod", bound=Callable[..., Awaitable[RequestScopes]]
)


# Request.meta key under which scope_cache persists the resolved scopes so that
# they survive a request being serialized to and restored from a disk queue.
_RESOLVED_SCOPES_META_KEY = "_throttling_resolved_scopes"


def scope_cache(f: _GetScopesMethod) -> _GetScopesMethod:
    """Decorator for :meth:`~ThrottlingManagerProtocol.get_scopes`
    implementations that persists the resolved scopes on ``request.meta``.

    The readers of the resolved scopes — the synchronous readiness API of a
    :ref:`throttling-aware scheduler <throttling-aware-scheduler>` and
    :meth:`~ThrottlingManagerProtocol.get_resolved_scopes` — read this persisted
    value instead of resolving the scopes again, so they stay cheap and
    consistent, and it survives a request being
    serialized to and restored from a :ref:`disk queue <topics-jobs>` (which is
    what lets the readiness API resolve the scopes of a restored request
    synchronously).

    The decorated method always re-resolves; it never reads the persisted value
    back. So a request that inherited ``request.meta`` from another one (e.g. a
    redirect built with :meth:`Request.replace() <scrapy.Request.replace>`,
    which copies ``meta``) resolves its own scopes and overwrites the inherited
    ones rather than reusing them.

    For example:

    .. code-block:: python

        from scrapy.utils.httpobj import urlparse_cached
        from scrapy.throttling import scope_cache


        class MyThrottlingManager:
            @scope_cache
            async def get_scopes(self, request):
                return urlparse_cached(request).hostname or ""
    """

    @wraps(f)
    async def wrapper(self: Any, request: Request) -> RequestScopes:
        scopes = await f(self, request)
        # Materialize one-shot iterables so the persisted value stays
        # re-iterable and serializable.
        if not isinstance(scopes, (str, dict)) and isinstance(scopes, Iterable):
            scopes = list(scopes)
        request.meta[_RESOLVED_SCOPES_META_KEY] = scopes
        return scopes

    return wrapper  # type: ignore[return-value]


class ThrottlingManager:
    """The default :setting:`THROTTLING_MANAGER` class.

    It assigns to each request its domain or subdomain as scope and handles
    backoff according to :ref:`backoff settings <basic-throttling>`.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def __init__(self, crawler: Crawler) -> None:
        self.crawler = crawler
        _warn_on_deprecated_concurrency(crawler.settings)
        self._debug = crawler.settings.getbool("THROTTLING_DEBUG")
        self._max_idle = crawler.settings.getfloat("THROTTLING_SCOPE_MAX_IDLE")
        self._robotstxt_obey = crawler.settings.getbool(
            "ROBOTSTXT_OBEY"
        ) and crawler.settings.getbool("THROTTLING_ROBOTSTXT_OBEY")
        self._robotstxt_max_delay = crawler.settings.getfloat(
            "THROTTLING_ROBOTSTXT_MAX_DELAY"
        )
        self._default_useragent: str = crawler.settings["USER_AGENT"]
        self._robotstxt_useragent: str | None = crawler.settings["ROBOTSTXT_USER_AGENT"]
        if self._robotstxt_obey:
            crawler.signals.connect(
                self._on_robots_parsed, signal=signals.robots_parsed
            )
        self._default_scope_manager_cls = load_object(
            crawler.settings["THROTTLING_SCOPE_MANAGER"]
        )
        self._scopes_config: dict[str, dict[str, Any]] = self._merge_download_slots(
            crawler.settings
        )
        # Ordered by least-recently-used first (see get_scope_manager), so the
        # scope limit can evict the coldest idle scopes (see THROTTLING_SCOPE_LIMIT).
        self._scope_managers: OrderedDict[ScopeID, ThrottlingScopeManagerProtocol] = (
            OrderedDict()
        )
        self._scope_limit: int = crawler.settings.getint("THROTTLING_SCOPE_LIMIT")
        self._last_eviction: float | None = None
        # Concurrency slots reserved by acquire(), to be released once the
        # request finishes downloading.
        self._reserved: WeakKeyDictionary[
            Request, list[tuple[ThrottlingScopeManagerProtocol, float | None]]
        ] = WeakKeyDictionary()

    @staticmethod
    def _merge_download_slots(settings: BaseSettings) -> dict[str, dict[str, Any]]:
        """Return the effective per-scope configuration, merging the deprecated
        :setting:`DOWNLOAD_SLOTS` setting into :setting:`THROTTLING_SCOPES`.

        Each ``DOWNLOAD_SLOTS`` entry is translated to a throttling scope keyed
        by the same slot name (the default manager keys domain scopes by host
        name, which is what download slots used too): ``concurrency`` and
        ``delay`` map directly, and the ``randomize_delay`` boolean maps to a
        ``jitter`` magnitude (the historical ±50%, or none). An explicit
        ``THROTTLING_SCOPES`` entry for the same scope takes precedence over the
        translated one. The deprecation warning is emitted by the downloader.
        """
        scopes: dict[str, dict[str, Any]] = {
            scope_id: dict(config)
            for scope_id, config in settings.getdict("THROTTLING_SCOPES").items()
        }
        for slot_id, slot_config in settings.getdict("DOWNLOAD_SLOTS").items():
            translated: dict[str, Any] = {}
            if "concurrency" in slot_config:
                translated["concurrency"] = slot_config["concurrency"]
            if "delay" in slot_config:
                translated["delay"] = slot_config["delay"]
            if "randomize_delay" in slot_config:
                translated["jitter"] = 0.5 if slot_config["randomize_delay"] else 0.0
            # An explicit THROTTLING_SCOPES entry wins over the translated one.
            scopes[slot_id] = {**translated, **scopes.get(slot_id, {})}
        return scopes

    @scope_cache
    async def get_scopes(self, request: Request) -> RequestScopes:
        return self._resolve_scopes_sync(request)

    def _resolve_scopes_sync(self, request: Request) -> RequestScopes:
        """Best-effort synchronous scope resolution.

        It backs :meth:`get_scopes` and is also the fallback for the synchronous
        readiness methods (:meth:`is_ready`, :meth:`reserve`,
        :meth:`get_time_until_ready`) when no scopes were persisted on
        ``request.meta`` by an earlier :meth:`get_scopes` call (which normally
        happens at enqueue time and survives disk restores; see
        :func:`scope_cache`). Subclasses whose :meth:`get_scopes` cannot be
        resolved synchronously rely on that persisted value instead.
        """
        scopes = request.meta.get("throttling_scopes")
        if scopes is not None:
            return cast("RequestScopes", scopes)
        download_slot = request.meta.get("download_slot")
        if download_slot is not None:
            warnings.warn(
                "The 'download_slot' request meta key is deprecated. Use "
                "'throttling_scopes' instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
            return cast("RequestScopes", download_slot)
        return urlparse_cached(request).hostname or ""

    def get_slot_key(self, request: Request) -> str:
        scopes = self._resolve_scopes_sync(request)
        scope_ids = sorted(iter_scopes(scopes))
        return "+".join(scope_ids) if scope_ids else ""

    def get_resolved_scopes(self, request: Request) -> RequestScopes:
        """Return the scopes under which *request* was (or will be) sent,
        reusing those persisted on ``request.meta`` by an earlier
        :meth:`get_scopes` call (see :func:`scope_cache`) and falling back to
        :meth:`_resolve_scopes_sync` only when none were persisted.

        The persisted value is authoritative: a request reaching a reader of
        this method (the readiness API, or a component reacting to its response)
        has already been enqueued and, for a request restored from a disk queue,
        re-resolving could attribute it to different scopes than the ones it was
        sent under.
        """
        if _RESOLVED_SCOPES_META_KEY in request.meta:
            return cast("RequestScopes", request.meta[_RESOLVED_SCOPES_META_KEY])
        return self._resolve_scopes_sync(request)

    def _cached_scope_values(
        self, request: Request
    ) -> list[tuple[ScopeID, float | None]]:
        """Return the ``(scope_id, quota_amount)`` pairs of *request*, from the
        scopes returned by :meth:`get_resolved_scopes`."""
        return list(iter_scope_values(self.get_resolved_scopes(request)))

    # -- Scope-state coordination (called from the request lifecycle) --------

    def get_scope_manager(self, scope_id: ScopeID) -> ThrottlingScopeManagerProtocol:
        manager = self._scope_managers.get(scope_id)
        if manager is not None:
            # Mark as most-recently-used for the LRU scope limit.
            self._scope_managers.move_to_end(scope_id)
            return manager
        config: dict[str, Any] = dict(self._scopes_config.get(scope_id, {}))
        config.setdefault("id", scope_id)
        manager_cls = (
            load_object(config["manager"])
            if "manager" in config
            else self._default_scope_manager_cls
        )
        manager = cast(
            "ThrottlingScopeManagerProtocol",
            build_from_crawler(manager_cls, self.crawler, config),
        )
        self._scope_managers[scope_id] = manager
        self._enforce_scope_limit(scope_id)
        return manager

    def _enforce_scope_limit(self, keep: ScopeID) -> None:
        """Evict least-recently-used idle scopes while the number of live scope
        managers exceeds :setting:`THROTTLING_SCOPE_LIMIT` (``0`` disables the
        limit).

        LRU order is kept by :meth:`get_scope_manager` moving each accessed
        scope to the end, so the coldest scopes are at the front. Only scopes
        that are idle (no in-flight requests and no active backoff) are evicted;
        the just-created *keep* scope is never evicted. A scope evicted while
        still throttling is simply recreated from its configuration the next
        time it is needed.
        """
        if self._scope_limit <= 0 or len(self._scope_managers) <= self._scope_limit:
            return
        now = time.monotonic()
        for scope_id in list(self._scope_managers):
            if len(self._scope_managers) <= self._scope_limit:
                break
            if scope_id != keep and self._scope_managers[scope_id].is_idle(now, 0):
                del self._scope_managers[scope_id]

    async def acquire(self, request: Request) -> None:
        # A throttling-aware scheduler reserves the request before handing it
        # to the engine, so there is nothing left to wait for or record here.
        if request in self._reserved:
            return
        now = time.monotonic()
        self._maybe_evict(now)
        await self._delay_request(request)
        scope_values = list(iter_scope_values(await self.get_scopes(request)))
        if not scope_values:
            return
        managers = [
            (self.get_scope_manager(scope_id), value)
            for scope_id, value in scope_values
        ]
        while True:
            wait = max(
                [0.0, *(manager.can_send(amount=value) for manager, value in managers)]
            )
            if wait > 0:
                if self._debug:
                    logger.debug(
                        f"Throttling {request} for {wait:.2f}s "
                        f"(scopes: {[scope_id for scope_id, _ in scope_values]})"
                    )
                await sleep(wait)
                continue
            # All time-based gates (delay, backoff, quota) are open; the only
            # remaining reason to wait is a full concurrency slot.
            blocked = [
                manager for manager, _ in managers if manager.concurrency_blocked()
            ]
            if not blocked:
                self._record_reservation(request, managers)
                return
            if self._debug:
                logger.debug(
                    f"Throttling {request} until a concurrency slot frees up "
                    f"(scopes: {[scope_id for scope_id, _ in scope_values]})"
                )
            await self._wait_for_slot(blocked)

    def _record_reservation(
        self,
        request: Request,
        managers: list[tuple[ThrottlingScopeManagerProtocol, float | None]],
    ) -> None:
        """Record a send on each of *request*'s scope *managers* and mark
        *request* as reserved, so :meth:`release` can later free the slots. This
        is the shared tail of :meth:`acquire` and :meth:`reserve`."""
        for manager, value in managers:
            manager.record_sent(amount=value)
        self._reserved[request] = managers

    def release(self, request: Request) -> None:
        managers = self._reserved.pop(request, None)
        if not managers:
            return
        for manager, _ in managers:
            manager.record_done()

    # -- Synchronous readiness API (used by a throttling-aware scheduler) ------

    def is_ready(self, request: Request) -> bool:
        now = time.monotonic()
        if self._request_delay_deadline(request, now) > now:
            return False
        for scope_id, value in self._cached_scope_values(request):
            manager = self.get_scope_manager(scope_id)
            if manager.can_send(now=now, amount=value) > 0:
                return False
            if manager.concurrency_blocked():
                return False
        return True

    def reserve(self, request: Request) -> None:
        # A throttling-aware scheduler reserves every request before handing it
        # to the engine, so acquire() always returns early for it and never
        # gets to evict idle scopes; do it here so their managers do not pile
        # up on broad crawls.
        self._maybe_evict(time.monotonic())
        managers = [
            (self.get_scope_manager(scope_id), value)
            for scope_id, value in self._cached_scope_values(request)
        ]
        self._record_reservation(request, managers)

    def get_time_until_ready(self, request: Request) -> float | None:
        now = time.monotonic()
        wait = max(0.0, self._request_delay_deadline(request, now) - now)
        for scope_id, value in self._cached_scope_values(request):
            manager = self.get_scope_manager(scope_id)
            wait = max(wait, manager.can_send(now=now, amount=value))
        return wait if wait > 0 else None

    def get_scope_load(self, scope_id: ScopeID) -> float:
        return self.get_scope_manager(scope_id).get_load()

    def get_request_delay(self, request: Request, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        return max(0.0, self._request_delay_deadline(request, now) - now)

    async def _wait_for_slot(self, managers: list[Any]) -> None:
        """Block until any of *managers* frees a concurrency slot.

        Each manager hands out an event Deferred that fires when a slot is freed
        (via :meth:`ThrottlingScopeManager.record_done`) or the limit is raised
        (via :meth:`ThrottlingScopeManager.set_concurrency`). A long safety timer
        bounds the wait in case no slot is ever freed (it always should be, via
        :meth:`release`).
        """
        pairs = [(manager, manager.slot_event()) for manager in managers]
        events = [event for _, event in pairs]
        _, pending = await wait_for_first(events, timeout=_SLOT_WAIT_TIMEOUT)
        for manager, event in pairs:
            if event in pending:
                manager.discard_slot_event(event)

    async def _delay_request(self, request: Request) -> None:
        """Honor the :reqmeta:`throttling_delay` meta key by holding *request*
        for the requested number of seconds the first time it is processed.

        This is the blocking (:meth:`acquire`) counterpart of
        :meth:`_request_delay_deadline`, which the readiness API polls instead;
        both share the deadline bookkeeping and the one-time debug log. Here the
        deadline is honored by sleeping until it, then marking the delay as
        consumed so the request is never held again."""
        now = time.monotonic()
        wait = self._request_delay_deadline(request, now) - now
        if wait <= 0:
            return
        await sleep(wait)
        request.meta["_throttling_delayed"] = True

    def _request_delay_deadline(self, request: Request, now: float) -> float:
        """Return the monotonic time before which *request* must not be sent due
        to its :reqmeta:`throttling_delay`, or ``0.0`` if it has none.

        This is the readiness-API counterpart of :meth:`_delay_request`:
        a throttling-aware scheduler gates requests through :meth:`is_ready` and
        :meth:`get_time_until_ready` instead of awaiting :meth:`acquire`, so the
        delay is enforced by holding back the request until this deadline rather
        than by sleeping. The deadline is computed once, the first time the
        request reaches the gate, and stored so later polls reuse it.

        A request whose delay has already been honored (the ``_throttling_delayed``
        flag, also set by :meth:`_delay_request`) is never delayed again,
        which keeps a resumed crawl from re-blocking on a stale deadline."""
        delay = request.meta.get("throttling_delay")
        if not delay or request.meta.get("_throttling_delayed"):
            return 0.0
        deadline = request.meta.get("_throttling_delay_deadline")
        if deadline is None:
            deadline = now + float(delay)
            request.meta["_throttling_delay_deadline"] = deadline
            if self._debug:
                logger.debug(f"Holding {request} for {delay:.2f}s (throttling_delay)")
        return deadline

    def back_off(
        self,
        scopes: RequestScopes,
        *,
        delay: float | None = None,
        cap: bool = True,
    ) -> None:
        for scope_id in iter_scopes(scopes):
            if self._debug:
                logger.debug(f"Backoff for scope {scope_id} (delay: {delay})")
            self.get_scope_manager(scope_id).record_backoff(delay=delay, cap=cap)

    def reconcile_quota(
        self,
        scopes: RequestScopes,
        *,
        consumed: float | None = None,
        remaining: float | None = None,
    ) -> None:
        for scope_id in iter_scopes(scopes):
            self.get_scope_manager(scope_id).reconcile_quota(
                consumed=consumed, remaining=remaining
            )

    def _on_robots_parsed(self, robotparser: Any, request: Request) -> None:
        """Honor a robots.txt ``Crawl-delay`` on the :signal:`robots_parsed`
        signal.

        It reads the ``Crawl-delay`` directive for the configured user agent from
        the parsed robots.txt and, if present, applies it to the scope of the
        host that *request* targets via :meth:`apply_robots_crawl_delay`.
        """
        if not self._robotstxt_obey:
            return
        useragent: str | bytes = self._robotstxt_useragent or self._default_useragent
        try:
            delay = robotparser.crawl_delay(useragent)
        except Exception:  # pragma: no cover - backend-specific failures
            return
        if delay:
            self.apply_robots_crawl_delay(
                urlparse_cached(request).hostname or "", delay
            )

    def apply_robots_crawl_delay(self, scope_id: ScopeID, delay: float) -> None:
        """Honor a robots.txt ``Crawl-delay`` directive of *delay* seconds for
        *scope_id* by setting its delay (capped at
        :setting:`THROTTLING_ROBOTSTXT_MAX_DELAY`) and its concurrency to ``1``.

        Called from the :signal:`robots_parsed` signal handler when
        :setting:`THROTTLING_ROBOTSTXT_OBEY` is enabled. An explicit
        :setting:`THROTTLING_SCOPES` configuration for the scope is respected, but
        a warning is logged about the discrepancy unless its ``ignore_robots_txt``
        key is ``True``.
        """
        if not self._robotstxt_obey:
            return
        capped = min(delay, self._robotstxt_max_delay)
        config = self._scopes_config.get(scope_id, {})
        if config.get("ignore_robots_txt"):
            return
        conflicts = []
        if config.get("delay") is not None and float(config["delay"]) < capped:
            conflicts.append(f"delay={config['delay']!r} < Crawl-delay {capped}")
        if config.get("concurrency") is not None and int(config["concurrency"]) > 1:
            conflicts.append(f"concurrency={config['concurrency']!r} > 1")
        if conflicts:
            logger.warning(
                f"Throttling scope {scope_id!r} is configured with {' and '.join(conflicts)}, "
                f"which is more aggressive than its robots.txt Crawl-delay of "
                f"{capped}s. The configured values take precedence; set "
                "'ignore_robots_txt': True in its THROTTLING_SCOPES entry to "
                "silence this warning."
            )
            return
        if self._debug:
            logger.debug(f"robots.txt Crawl-delay for scope {scope_id}: {capped}s")
        manager = self.get_scope_manager(scope_id)
        manager.set_base_delay(capped)
        manager.set_concurrency(1)

    def delay_scope(self, scope_id: ScopeID, delay: float) -> None:
        # Like a Retry-After / RateLimit-Reset header, this gates the scope's
        # next request by delay seconds (a one-time hold, not a steady-state
        # delay); unlike those, it is trusted, so it bypasses BACKOFF_MAX_DELAY.
        self.back_off(scope_id, delay=float(delay), cap=False)

    def get_scope_delay(self, scope_id: ScopeID) -> float:
        return self.get_scope_manager(scope_id).get_base_delay()

    def set_scope_delay(self, scope_id: ScopeID, delay: float) -> None:
        self.get_scope_manager(scope_id).set_base_delay(
            float(delay), only_increase=False
        )

    def _maybe_evict(self, now: float) -> None:
        if self._max_idle <= 0:
            return
        if (
            self._last_eviction is not None
            and now - self._last_eviction < self._max_idle / 2
        ):
            return
        self._last_eviction = now
        for scope_id in list(self._scope_managers):
            if self._scope_managers[scope_id].is_idle(now, self._max_idle):
                del self._scope_managers[scope_id]


class ThrottlingScopeManagerProtocol(Protocol):
    """A protocol for :setting:`THROTTLING_SCOPE_MANAGER` :ref:`components
    <topics-components>`.

    The ``__init__`` method gets a ``config`` dict with the base configuration
    of the managed throttling scope. For example:

    .. code-block:: python

        {
            "id": "example.com",
            "concurrency": 1,
            "delay": 1.0,
            "jitter": 0.5,
            "quota": 1000.0,
            "window": 60.0,
            "backoff": {
                "http_codes": [429, 503],
                "exceptions": ["builtins.IOError"],
                "delay_factor": 1.2,
                "max_delay": 180.0,
                "min_delay": 5.0,
                "jitter": [0.01, 0.33],
            },
            "rampup": {
                "backoff_target": 1,
                "delay_factor": 0.5,
                "min_delay": 0.05,
            },
        }

    """

    @classmethod
    def from_crawler(cls, crawler: Crawler, config: dict[str, Any]) -> Self: ...

    def __init__(self, crawler: Crawler, config: dict[str, Any]) -> None: ...

    def can_send(self, now: float | None = None, amount: float | None = None) -> float:
        """Return the number of seconds to wait before a request for this scope
        may be sent, or ``0`` if it may be sent right away.

        *amount* is the expected :ref:`throttling quota <throttling-quotas>`
        consumption of the request, if any.
        """

    def record_sent(
        self, now: float | None = None, amount: float | None = None
    ) -> None:
        """Record that a request for this scope has just been sent, consuming
        *amount* of its :ref:`throttling quota <throttling-quotas>` if given."""

    def record_done(self, now: float | None = None) -> None:
        """Record that a previously :meth:`record_sent` request has finished
        downloading, freeing its concurrency slot."""

    def record_backoff(
        self,
        delay: float | None = None,
        now: float | None = None,
        cap: bool = True,
    ) -> None:
        """Apply a backoff to this scope.

        *delay*, when given, is a hard minimum delay in seconds (e.g. from a
        ``Retry-After`` header). When omitted, an exponential backoff step is
        applied instead.

        *cap* limits *delay* to :setting:`BACKOFF_MAX_DELAY`. It is ``True`` for
        untrusted input such as response headers, and may be set to ``False``
        for trusted, programmatic delays (see
        :meth:`ThrottlingManagerProtocol.delay_scope`).
        """

    def reconcile_quota(
        self,
        consumed: float | None = None,
        remaining: float | None = None,
        now: float | None = None,
    ) -> None:
        """Reconcile the :ref:`throttling quota <throttling-quotas>` of this
        scope with the actual *consumed* amount (or the *remaining* amount)
        reported for a request, correcting the estimate used by
        :meth:`record_sent`."""

    def triggers_backoff_for_status(self, status: int) -> bool:
        """Return whether a response with the given *status* triggers backoff
        for this scope (defaults to :setting:`BACKOFF_HTTP_CODES`)."""

    def triggers_backoff_for_exception(self, exception: BaseException) -> bool:
        """Return whether *exception* triggers backoff for this scope (defaults
        to :setting:`BACKOFF_EXCEPTIONS`)."""

    def get_base_delay(self) -> float:
        """Return the base (non-backoff) delay of this scope, in seconds."""

    def set_base_delay(self, delay: float, *, only_increase: bool = True) -> None:
        """Set the base (non-backoff) delay of this scope to *delay* seconds.

        By default it only raises the delay, to honor external hints such as a
        robots.txt ``Crawl-delay`` directive. Pass ``only_increase=False`` to
        also allow lowering it.
        """

    def set_concurrency(self, concurrency: int) -> None:
        """Set the maximum number of concurrent requests allowed for this
        scope."""

    def concurrency_blocked(self) -> bool:
        """Return whether this scope is at its concurrency limit.

        :class:`ThrottlingManager` calls this (after all time-based gates in
        :meth:`can_send` are open) to decide whether to wait for a freed slot.
        Return ``False`` when no concurrency limit is enforced.
        """

    def get_load(self) -> float:
        """Return the current load of this scope: a non-negative number, with
        ``1.0`` meaning "as busy as its concurrency limit allows".

        A :ref:`throttling-aware scheduler <throttling-aware-scheduler>` uses
        this to break ties between equally-prioritized requests, preferring the
        least-loaded scopes. The reference implementation returns active sends
        divided by the concurrency limit (falling back to
        :setting:`CONCURRENT_REQUESTS` when the scope enforces no explicit
        limit), but any consistent busyness metric works; return ``0.0`` when
        none is meaningful.
        """

    def slot_event(self) -> Deferred[None]:
        """Return a :class:`~twisted.internet.defer.Deferred` that fires when
        a concurrency slot next becomes available (e.g. when
        :meth:`record_done` is called or the limit is raised via
        :meth:`set_concurrency`)."""

    def discard_slot_event(self, event: Deferred[None]) -> None:
        """Cancel a pending slot event returned by :meth:`slot_event`.

        Called by :class:`ThrottlingManager` when the wait ends without the
        event firing (e.g. another scope's slot opened first).
        """

    def is_idle(self, now: float, max_idle: float) -> bool:
        """Return whether this scope can be evicted from memory.

        A scope is idle when it has not been used for *max_idle* seconds and is
        not currently in an active (future) backoff.
        """


# Safety timeout for acquire() while it waits, event-driven, for a concurrency
# slot to free up: a slot_event normally fires first (from record_done() or
# set_concurrency()); this only guards against a request that never reaches
# release() so the wait can never hang forever.
_SLOT_WAIT_TIMEOUT = 1.0


class ThrottlingScopeManager:
    """The default :setting:`THROTTLING_SCOPE_MANAGER` class.

    It implements a per-scope state machine covering delay, exponential
    :ref:`backoff <backoff>`, :ref:`rampup <rampup>`, concurrency and
    :ref:`quotas <throttling-quotas>`:

    -   A base delay (the scope ``"delay"`` config, defaulting to
        :setting:`DOWNLOAD_DELAY`) is enforced between consecutive requests for
        the scope.

    -   On a backoff trigger (a :setting:`BACKOFF_HTTP_CODES` response or a
        :setting:`BACKOFF_EXCEPTIONS` exception) the delay grows exponentially
        by :setting:`BACKOFF_DELAY_FACTOR`, bounded by :setting:`BACKOFF_MIN_DELAY`
        and :setting:`BACKOFF_MAX_DELAY`, with :setting:`BACKOFF_JITTER` applied.
        A ``Retry-After`` / ``RateLimit-Reset`` delay additionally holds the
        scope back until that time before its next request (a one-time gate,
        capped at :setting:`BACKOFF_MAX_DELAY`), without becoming the
        steady-state delay.

    -   After :setting:`BACKOFF_WINDOW` seconds without a new trigger, the delay
        recovers one step at a time back towards the base delay.

    -   When the scope is configured with a ``"concurrency"`` limit (or with
        ``"rampup"``), no more than that many requests are allowed in flight at
        once.

    -   When the scope sets ``"rampup": True``, throughput is increased every
        :setting:`BACKOFF_WINDOW` that stays under :setting:`RAMPUP_BACKOFF_TARGET`
        backoff triggers, first by lowering the delay and then by raising the
        concurrency limit.

    -   When the scope is configured with a ``"quota"``, no more than that much
        quota is consumed per ``"window"`` (default: :setting:`THROTTLING_WINDOW`).
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler, config: dict[str, Any]) -> Self:
        return cls(crawler, config)

    def __init__(self, crawler: Crawler, config: dict[str, Any]) -> None:
        settings = crawler.settings
        backoff: dict[str, Any] = config.get("backoff", {})
        self._id: ScopeID = config.get("id", "")
        # The per-scope delay defaults to DOWNLOAD_DELAY; a scope can override
        # it with its own "delay" config (see THROTTLING_SCOPES).
        self._base_delay: float = float(
            config.get("delay", settings.getfloat("DOWNLOAD_DELAY"))
        )
        # Magnitude of the random variation applied to the (non-backoff) delay,
        # normalized to a (low, high) multiplier range (or None for no jitter).
        # Defaults to RANDOMIZE_DOWNLOAD_DELAY's historical ±50% when delay
        # randomization is on, or to no variation when it is off.
        self._jitter: tuple[float, float] | None = self._normalize_jitter(
            config.get(
                "jitter", 0.5 if settings.getbool("RANDOMIZE_DOWNLOAD_DELAY") else 0.0
            )
        )
        self._delay_factor: float = float(
            backoff.get("delay_factor", settings.getfloat("BACKOFF_DELAY_FACTOR"))
        )
        self._max_delay: float = float(
            backoff.get("max_delay", settings.getfloat("BACKOFF_MAX_DELAY"))
        )
        self._min_delay: float = float(
            backoff.get("min_delay", settings.getfloat("BACKOFF_MIN_DELAY"))
        )
        self._backoff_jitter: tuple[float, float] | None = self._normalize_jitter(
            backoff.get("jitter", settings.getfloat("BACKOFF_JITTER"))
        )
        # Which responses/exceptions trigger backoff for this scope. Each
        # defaults to the matching global BACKOFF_* setting (see
        # triggers_backoff_for_status / triggers_backoff_for_exception).
        self._backoff_http_codes: set[int] = {
            int(code)
            for code in backoff.get(
                "http_codes", settings.getlist("BACKOFF_HTTP_CODES")
            )
        }
        self._backoff_exceptions: tuple[type[BaseException], ...] = _load_exceptions(
            backoff.get("exceptions", settings.getlist("BACKOFF_EXCEPTIONS"))
        )
        self._window: float = settings.getfloat("BACKOFF_WINDOW")

        # Rampup.
        rampup = config.get("rampup")
        self._rampup_enabled: bool = bool(rampup)
        rampup_config: dict[str, Any] = rampup if isinstance(rampup, dict) else {}
        self._rampup_target: float = float(
            rampup_config.get(
                "backoff_target", settings.getfloat("RAMPUP_BACKOFF_TARGET")
            )
        )
        self._rampup_delay_factor: float = float(rampup_config.get("delay_factor", 0.5))
        self._rampup_min_delay: float = float(rampup_config.get("min_delay", 0.0))

        # Concurrency. ``None`` means no scope-level limit (the downloader slots
        # enforce concurrency instead); a limit is only set when configured
        # explicitly or implied by rampup.
        configured_concurrency = config.get("concurrency")
        if configured_concurrency is not None:
            self._concurrency: int | None = int(configured_concurrency)
        elif self._rampup_enabled:
            # Rampup starts conservative at a single slot and probes upward.
            self._concurrency = 1
        else:
            self._concurrency = _default_scope_concurrency(settings) or None
        # Used as the load denominator when the scope enforces no explicit
        # concurrency limit (see get_load()).
        self._global_concurrency: int = settings.getint("CONCURRENT_REQUESTS")

        # Quota.
        quota = config.get("quota")
        self._quota: float | None = None if quota is None else float(quota)
        self._quota_window: float = float(
            config.get("window", settings.getfloat("THROTTLING_WINDOW"))
        )

        # State.
        self._delay: float = self._base_delay
        self._backoff_level: int = 0
        self._next_allowed_time: float | None = None
        self._in_backoff_until: float | None = None
        self._last_backoff_time: float | None = None
        self._last_seen: float | None = None
        self._active: int = 0
        self._slot_waiters: list[Deferred[None]] = []
        self._consumed: float = 0.0
        self._quota_window_start: float | None = None
        self._rampup_window_start: float | None = None
        self._rampup_backoffs: int = 0

    @staticmethod
    def _now(now: float | None) -> float:
        return time.monotonic() if now is None else now

    @staticmethod
    def _normalize_jitter(
        jitter: float | list[float],
    ) -> tuple[float, float] | None:
        """Normalize a ``jitter`` config value to a ``(low, high)`` multiplier
        range, or ``None`` when no jitter applies.

        A scalar ``j`` means the symmetric range ``(-j, +j)``, so that
        ``value * (1 + uniform(-j, +j))`` matches the historical
        ``value * uniform(1 - j, 1 + j)``; a list/tuple is taken as an explicit
        ``[low, high]`` range.
        """
        if isinstance(jitter, (list, tuple)):
            return (float(jitter[0]), float(jitter[1]))
        if not jitter:
            return None
        return (-float(jitter), float(jitter))

    @staticmethod
    def _apply_jitter(value: float, jitter: tuple[float, float] | None) -> float:
        if jitter is None:
            return value
        return value * (1 + random.uniform(*jitter))  # noqa: S311

    def _effective_delay(self) -> float:
        # ``self._delay`` is the deterministic delay (the base delay, or the
        # bounded exponential value while backing off); jitter is applied here,
        # per use, so successive delays spread out without compounding and
        # without piling probability mass on the min/max bounds (which clipping
        # a jittered value would do). While backing off, the backoff jitter
        # applies; otherwise the plain delay jitter does.
        if self._delay <= 0:
            return self._delay
        jitter = self._backoff_jitter if self._backoff_level > 0 else self._jitter
        return self._apply_jitter(self._delay, jitter)

    def _recover(self, now: float) -> None:
        if self._backoff_level == 0 or self._last_backoff_time is None:
            return
        if self._window <= 0:
            # A non-positive window has no recovery cadence to step through (and
            # would spin forever on a zero-length step), so recover at once.
            self._backoff_level = 0
            self._delay = self._base_delay
            self._in_backoff_until = None
            self._last_backoff_time = None
            return
        while self._backoff_level > 0 and now - self._last_backoff_time >= self._window:
            self._backoff_level -= 1
            self._last_backoff_time += self._window
            if self._backoff_level == 0:
                self._delay = self._base_delay
                self._in_backoff_until = None
                self._last_backoff_time = None
                break
            self._delay = max(self._base_delay, self._delay / self._delay_factor)

    def _maybe_rampup(self, now: float) -> None:
        """Increase throughput once per :setting:`BACKOFF_WINDOW` that stays
        under :setting:`RAMPUP_BACKOFF_TARGET` backoff triggers."""
        if not self._rampup_enabled:
            return
        if self._window <= 0:
            # No window means no cadence to ramp up on (and a zero-length step
            # would spin forever).
            return
        if self._rampup_window_start is None:
            self._rampup_window_start = now
            return
        if now - self._rampup_window_start < self._window:
            return
        # Catch up with elapsed time but apply at most one ramp step per call: a
        # scope that stayed idle for several windows must not ramp up
        # cumulatively once it becomes active again (that would collapse the
        # delay or jump the concurrency limit by several steps at once).
        elapsed_windows = int((now - self._rampup_window_start) // self._window)
        self._rampup_window_start += elapsed_windows * self._window
        if self._rampup_backoffs < self._rampup_target:
            self._rampup_step()
        self._rampup_backoffs = 0

    def _rampup_step(self) -> None:
        # Backoff in progress: let it recover before probing again.
        if self._backoff_level > 0:
            return
        if self._delay > self._rampup_min_delay:
            # Lower only the effective delay while probing for headroom; the
            # configured base delay is left untouched so it stays the recovery
            # target on backoff and the value reported by get_base_delay().
            self._delay = max(
                self._rampup_min_delay, self._delay * self._rampup_delay_factor
            )
        else:
            # Rampup is only enabled with a concurrency limit set.
            assert self._concurrency is not None
            self._concurrency += 1

    def _maybe_reset_quota(self, now: float) -> None:
        if self._quota is None:
            return
        if self._quota_window <= 0:
            # A non-positive window has no reset cadence to step through (and
            # would spin forever on a zero-length step), so keep it reset.
            self._consumed = 0.0
            self._quota_window_start = now
            return
        if self._quota_window_start is None:
            self._quota_window_start = now
            return
        while now - self._quota_window_start >= self._quota_window:
            self._quota_window_start += self._quota_window
            self._consumed = 0.0

    def can_send(self, now: float | None = None, amount: float | None = None) -> float:
        # can_send() only refreshes passive, time-based state (backoff recovery
        # and the quota window) to reflect the current time; it performs no
        # active throughput probing. That way a readiness check (is_ready() /
        # get_time_until_ready()) has no side effect on the send rate: rampup
        # only advances on an actual send, from record_sent().
        now = self._now(now)
        self._recover(now)
        self._maybe_reset_quota(now)
        waits = [0.0]
        if self._in_backoff_until is not None:
            waits.append(self._in_backoff_until - now)
        if self._next_allowed_time is not None:
            waits.append(self._next_allowed_time - now)
        if self._quota is not None:
            need = 0.0 if amount is None else float(amount)
            # Block until the window resets only if some quota is already spent;
            # a single oversized request is always allowed through.
            if self._consumed > 0 and self._consumed + need > self._quota:
                start = self._quota_window_start or now
                waits.append(start + self._quota_window - now)
        # Concurrency is enforced separately, via concurrency_blocked() and
        # slot_event(), so acquire() can wait for a freed slot without polling.
        return max(waits)

    def record_sent(
        self, now: float | None = None, amount: float | None = None
    ) -> None:
        now = self._now(now)
        self._last_seen = now
        if self._in_backoff_until is not None and now >= self._in_backoff_until:
            self._in_backoff_until = None
        # An actual send is the cue to probe for more throughput (rampup),
        # rather than a mere readiness check; see can_send().
        self._maybe_rampup(now)
        self._next_allowed_time = now + self._effective_delay()
        self._active += 1
        if self._quota is not None and amount is not None:
            self._maybe_reset_quota(now)
            self._consumed += float(amount)

    def record_done(self, now: float | None = None) -> None:
        if self._active > 0:
            self._active -= 1
            self._fire_slot_waiters()

    def concurrency_blocked(self) -> bool:
        return self._concurrency is not None and self._active >= self._concurrency

    def get_load(self) -> float:
        limit = (
            self._concurrency
            if self._concurrency is not None
            else self._global_concurrency
        )
        if not limit:
            return 0.0
        return self._active / limit

    def slot_event(self) -> Deferred[None]:
        """Return a Deferred that fires when a concurrency slot next frees up
        (via :meth:`record_done`) or the limit is raised (via
        :meth:`set_concurrency`)."""
        event: Deferred[None] = Deferred()
        self._slot_waiters.append(event)
        return event

    def discard_slot_event(self, event: Deferred[None]) -> None:
        with contextlib.suppress(ValueError):
            self._slot_waiters.remove(event)

    def _fire_slot_waiters(self) -> None:
        waiters, self._slot_waiters = self._slot_waiters, []
        for event in waiters:
            if not event.called:
                event.callback(None)

    def record_backoff(
        self,
        delay: float | None = None,
        now: float | None = None,
        cap: bool = True,
    ) -> None:
        now = self._now(now)
        self._last_seen = now
        self._last_backoff_time = now
        self._backoff_level += 1
        self._rampup_backoffs += 1
        if delay is not None:
            # A hard delay (e.g. a Retry-After header) is a one-time gate: hold
            # the scope back for at least this long *once*, matching the HTTP
            # semantics of "do not retry before this time". It is deliberately
            # not turned into the steady-state inter-request delay; the delay
            # still grows by one exponential step below (and recovers over
            # BACKOFF_WINDOW), so a small Retry-After does not become a long
            # standing delay for every later request.
            hard = min(float(delay), self._max_delay) if cap else float(delay)
            self._in_backoff_until = now + hard
        grown = self._delay * self._delay_factor if self._delay > 0 else self._min_delay
        # Store the deterministic, bounded delay; jitter is applied per use in
        # _effective_delay(), so it neither compounds across successive backoff
        # steps nor concentrates on BACKOFF_MIN_DELAY / BACKOFF_MAX_DELAY.
        self._delay = min(max(self._min_delay, grown), self._max_delay)
        self._next_allowed_time = now + self._effective_delay()

    def reconcile_quota(
        self,
        consumed: float | None = None,
        remaining: float | None = None,
        now: float | None = None,
    ) -> None:
        if self._quota is None:
            return
        self._maybe_reset_quota(self._now(now))
        if remaining is not None:
            self._consumed = max(0.0, self._quota - float(remaining))
        elif consumed is not None:
            self._consumed = max(0.0, self._consumed + float(consumed))

    def triggers_backoff_for_status(self, status: int) -> bool:
        return status in self._backoff_http_codes

    def triggers_backoff_for_exception(self, exception: BaseException) -> bool:
        return isinstance(exception, self._backoff_exceptions)

    def get_base_delay(self) -> float:
        return self._base_delay

    def set_base_delay(self, delay: float, *, only_increase: bool = True) -> None:
        if only_increase and delay <= self._base_delay:
            return
        self._base_delay = delay
        # Reflect the change in the effective delay unless a backoff is raising
        # it above the base right now.
        if self._backoff_level == 0:
            self._delay = delay

    def set_concurrency(self, concurrency: int) -> None:
        self._concurrency = max(1, int(concurrency))
        self._fire_slot_waiters()

    def is_idle(self, now: float, max_idle: float) -> bool:
        if self._in_backoff_until is not None and self._in_backoff_until > now:
            return False
        if self._active > 0:
            return False
        if self._last_seen is None:
            return True
        return (now - self._last_seen) > max_idle
