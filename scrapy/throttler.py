from __future__ import annotations

import contextlib
import json
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
    entries.
    """

    enabled: bool
    """Whether :ref:`backoff <backoff>` applies to this scope. Defaults to
    ``True``; set it to ``False`` to disable backoff for the scope, so it relies
    solely on its configured delay and quota."""

    http_codes: list[int]
    """Per-scope override of :setting:`BACKOFF_HTTP_CODES`."""

    exceptions: list[str]
    """Per-scope override of :setting:`BACKOFF_EXCEPTIONS`."""

    max_delay: float
    """Per-scope override of :setting:`BACKOFF_MAX_DELAY`."""


class ThrottlingScopeConfig(TypedDict, total=False):
    """Accepted keys of :setting:`THROTTLING_SCOPES` entries."""

    concurrency: int
    """Per-scope override of :setting:`THROTTLING_SCOPE_CONCURRENCY`."""

    delay: float
    """Per-scope override of :setting:`DOWNLOAD_DELAY`."""

    jitter: float | list[float]
    """Magnitude of the random variation applied to ``delay``; the per-scope
    override of :setting:`RANDOMIZE_DOWNLOAD_DELAY` (``0`` disables it, ``0.5``
    means ±50%)."""

    quota: float
    """Maximum :ref:`throttler quota <throttling-quotas>` the scope may consume
    per ``window``. Unlimited when unset."""

    window: float
    """Length in seconds of the ``quota`` window; per-scope override of
    :setting:`THROTTLER_WINDOW`."""

    manager: str | type
    """Import path or class of a custom :setting:`THROTTLING_SCOPE_MANAGER` for
    this scope."""

    backoff: BackoffConfig
    """Per-scope override of the :ref:`backoff <backoff>` settings; see
    :class:`BackoffConfig`."""

    ignore_robots_txt: bool
    """Silence the warning logged when this configuration is more aggressive
    than a robots.txt ``Crawl-delay``."""


ScopeID = str
QuotaAmount = float
ScopeQuotas = dict[ScopeID, QuotaAmount | None]
JitterRange = tuple[float, float]  # (low, high) multiplier range
RequestScopes = None | ScopeID | Iterable[ScopeID] | ScopeQuotas


def iter_scopes(scopes: RequestScopes) -> Iterable[ScopeID]:
    """Iterate over the scope IDs of *scopes*, whatever its form.

    :class:`~ThrottlerProtocol.get_scopes` (and
    :meth:`~ThrottlerProtocol.get_resolved_scopes`) may return a single
    scope ID, an iterable of them, a ``{scope_id: quota}`` mapping, or ``None``;
    this helper normalizes any of those into an iterable of scope IDs, e.g. to
    react to a request's scopes in a custom middleware.
    """
    return (scope for scope, _ in iter_scope_quota_amounts(scopes))


def iter_scope_quota_amounts(
    scopes: RequestScopes,
) -> Iterable[tuple[ScopeID, QuotaAmount | None]]:
    """Iterate over *scopes* as ``(scope_id, quota_amount)`` pairs.

    For dict scopes the quota amount is the expected :ref:`throttler quota
    <throttling-quotas>` consumption; for every other form it is ``None``.
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
    :meth:`Throttler.__init__`).

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


def _warn_on_unachievable_concurrency(settings: BaseSettings) -> None:
    """Warn about configured concurrency limits that exceed
    :setting:`CONCURRENT_REQUESTS`. Call once per crawl (see
    :meth:`Throttler.__init__`).

    :setting:`CONCURRENT_REQUESTS` caps the total number of requests in flight,
    so a per-scope (or per-domain) concurrency limit above it can never be
    reached.
    """
    global_concurrency = settings.getint("CONCURRENT_REQUESTS")
    offenders: list[str] = [
        f"{name}={settings.getint(name)}"
        for name in ("CONCURRENT_REQUESTS_PER_DOMAIN", "THROTTLING_SCOPE_CONCURRENCY")
        if settings.getint(name) > global_concurrency
    ]
    offenders += [
        f"THROTTLING_SCOPES[{scope_id!r}]['concurrency']={config['concurrency']}"
        for scope_id, config in settings.getdict("THROTTLING_SCOPES").items()
        if config.get("concurrency") is not None
        and int(config["concurrency"]) > global_concurrency
    ]
    if offenders:
        logger.warning(
            f"The following concurrency settings exceed CONCURRENT_REQUESTS "
            f"({global_concurrency}), which caps the total number of requests in "
            f"flight, so they cannot be reached: {', '.join(offenders)}."
        )


def _to_scope_dict(scopes: RequestScopes) -> ScopeQuotas:
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
    quota_amount: QuotaAmount | None = None,
    /,
) -> ScopeQuotas:
    """Add *scope* to *scopes* with *quota_amount*, returning a
    ``{scope_id: quota}`` dict.

    This is a utility function to help extending the output of
    :meth:`~ThrottlerProtocol.get_scopes`, e.g. in
    :class:`Throttler` subclasses.

    Adding a scope with a *quota_amount* fails if it is already present, so an
    existing :ref:`quota <throttling-quotas>` is never silently overwritten;
    adding it without a quota amount leaves any existing entry untouched.
    """
    result = _to_scope_dict(scopes)
    if quota_amount is None:
        result.setdefault(scope, None)
        return result
    if scope in result:
        raise TypeError(f"Scope {scope!r} already has a quota amount in {scopes!r}")
    result[scope] = quota_amount
    return result


class ThrottlerProtocol(Protocol):
    """A protocol for :setting:`THROTTLER` :ref:`components
    <topics-components>`."""

    async def get_scopes(self, request: Request) -> RequestScopes:
        """Return the :ref:`throttling scopes <throttling-scopes>` that apply
        to *request*.

        Return ``None`` if no scopes apply, a string for a single scope, an
        iterable of strings for multiple scopes, or a dict with scope IDs as
        keys and :ref:`throttler quotas <throttling-quotas>` as values.
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
        used by a :ref:`throttler-aware scheduler
        <throttler-aware-scheduler>` to decide whether a request can be
        dequeued now. It assumes the scopes of *request* have already been
        resolved (e.g. by an earlier :meth:`get_scopes` call at enqueue time).
        """

    def reserve(self, request: Request) -> None:
        """Claim a send for *request*: record the send on every one of its
        scopes and mark *request* as reserved, so that a later :meth:`acquire`
        for it returns immediately without reserving again.

        A :ref:`throttler-aware scheduler <throttler-aware-scheduler>` calls
        this when it decides to dequeue *request* (after :meth:`is_ready`
        returned ``True``). The reservation is released by :meth:`release`.
        """

    def get_time_until_ready(self, request: Request) -> float | None:
        """Return the number of seconds until every time-based gate of
        *request* would be open, or ``None`` if no time-based gate is currently
        blocking it (only a concurrency slot could be).

        Used by a :ref:`throttler-aware scheduler
        <throttler-aware-scheduler>` to schedule a wakeup when all pending
        requests are time-blocked.
        """

    def get_scopes_key(self, request: Request) -> str:
        """Return a single string key for *request*, derived from its scopes.

        For a single scope this is the scope ID itself (so the key of a
        single-domain request matches its historical ``download_slot``); for
        multiple scopes the sorted scope IDs are JSON-encoded into an
        order-independent, collision-free key. This is the synchronous
        counterpart of :meth:`get_scopes`, used wherever a plain string key is
        needed (e.g. scheduler priority queues).
        """

    def get_scope_load(self, scope_id: str) -> float:
        """Return the current load of the scope identified by *scope_id*: its
        active sends divided by its concurrency limit (or by the global
        :setting:`CONCURRENT_REQUESTS` when the scope has no explicit limit).

        Used by a :ref:`throttler-aware scheduler
        <throttler-aware-scheduler>` to balance dequeuing across scopes,
        preferring the least-loaded ones.
        """

    def get_request_delay(self, request: Request, now: float | None = None) -> float:
        """Return how many seconds *request* must still be held individually
        because of its :reqmeta:`delay`, or ``0.0`` if it has none
        or it has already elapsed. The one-time delay is started on the first
        call.

        Unlike a scope delay, this affects only *request*: a
        :ref:`throttler-aware scheduler <throttler-aware-scheduler>` must
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

        A backoff step is always applied to the scope's delay.
        When *delay* is given, the scope is *additionally* held back for at
        least *delay* seconds before its next request: a one-time gate (e.g.
        from a :ref:`Retry-After <retry-after>` header), not a change to the
        steady-state delay. *cap* limits *delay* to :setting:`BACKOFF_MAX_DELAY`;
        set it to ``False`` for trusted, programmatic delays.
        """

    def reconcile_quota(
        self,
        scopes: RequestScopes,
        *,
        consumed: float | None = None,
        remaining: float | None = None,
    ) -> None:
        """Reconcile the :ref:`throttler quota <throttling-quotas>` of each of
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

        Unlike :meth:`back_off`, this both raises and lowers the delay and is
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
_RESOLVED_SCOPES_META_KEY = "_throttler_resolved_scopes"


def scope_cache(f: _GetScopesMethod) -> _GetScopesMethod:
    """Decorator for :meth:`~ThrottlerProtocol.get_scopes`
    implementations that persists the resolved scopes on ``request.meta``.

    The readers of the resolved scopes — the synchronous readiness API of a
    :ref:`throttler-aware scheduler <throttler-aware-scheduler>` and
    :meth:`~ThrottlerProtocol.get_resolved_scopes` — read this persisted
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
        from scrapy.throttler import scope_cache


        class MyThrottler:
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


class Throttler:
    """The default :setting:`THROTTLER` class.

    It assigns to each request its domain or subdomain as scope and handles
    backoff according to :ref:`backoff settings <basic-throttling>`.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def __init__(self, crawler: Crawler) -> None:
        self.crawler = crawler
        _warn_on_deprecated_concurrency(crawler.settings)
        _warn_on_unachievable_concurrency(crawler.settings)
        self._debug = crawler.settings.getbool("THROTTLER_DEBUG")
        self._max_idle = crawler.settings.getfloat("THROTTLING_SCOPE_MAX_IDLE")
        self._robotstxt_obey = crawler.settings.getbool(
            "ROBOTSTXT_OBEY"
        ) and crawler.settings.getbool("THROTTLER_ROBOTSTXT_OBEY")
        self._robotstxt_max_delay = crawler.settings.getfloat(
            "THROTTLER_ROBOTSTXT_MAX_DELAY"
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
            Request, list[tuple[ThrottlingScopeManagerProtocol, QuotaAmount | None]]
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

    def get_scopes_key(self, request: Request) -> str:
        scopes = self._resolve_scopes_sync(request)
        scope_ids = sorted(iter_scopes(scopes))
        if not scope_ids:
            return ""
        if len(scope_ids) == 1:
            return scope_ids[0]
        return json.dumps(scope_ids)

    def get_resolved_scopes(self, request: Request) -> RequestScopes:
        if _RESOLVED_SCOPES_META_KEY in request.meta:
            return cast("RequestScopes", request.meta[_RESOLVED_SCOPES_META_KEY])
        return self._resolve_scopes_sync(request)

    def _cached_scope_quota_amounts(
        self, request: Request
    ) -> list[tuple[ScopeID, QuotaAmount | None]]:
        """Return the ``(scope_id, quota_amount)`` pairs of *request*, from the
        scopes returned by :meth:`get_resolved_scopes`."""
        return list(iter_scope_quota_amounts(self.get_resolved_scopes(request)))

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
        # A throttler-aware scheduler reserves the request before handing it
        # to the engine, so there is nothing left to wait for or record here.
        if request in self._reserved:
            return
        now = time.monotonic()
        self._maybe_evict(now)
        await self._delay_request(request)
        scope_values = list(iter_scope_quota_amounts(await self.get_scopes(request)))
        if not scope_values:
            return
        managers = [
            (self.get_scope_manager(scope_id), quota_amount)
            for scope_id, quota_amount in scope_values
        ]
        while True:
            wait = max(
                [
                    0.0,
                    *(
                        manager.can_send(quota_amount=quota_amount)
                        for manager, quota_amount in managers
                    ),
                ]
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
        managers: list[tuple[ThrottlingScopeManagerProtocol, QuotaAmount | None]],
    ) -> None:
        """Record a send on each of *request*'s scope *managers* and mark
        *request* as reserved, so :meth:`release` can later free the slots. This
        is the shared tail of :meth:`acquire` and :meth:`reserve`."""
        for manager, quota_amount in managers:
            manager.record_sent(quota_amount=quota_amount)
        self._reserved[request] = managers

    def release(self, request: Request) -> None:
        managers = self._reserved.pop(request, None)
        if not managers:
            return
        for manager, _ in managers:
            manager.record_done()

    # -- Synchronous readiness API (used by a throttler-aware scheduler) ------

    def is_ready(self, request: Request) -> bool:
        now = time.monotonic()
        if self._request_delay_deadline(request, now) > now:
            return False
        for scope_id, quota_amount in self._cached_scope_quota_amounts(request):
            manager = self.get_scope_manager(scope_id)
            if manager.can_send(now=now, quota_amount=quota_amount) > 0:
                return False
            if manager.concurrency_blocked():
                return False
        return True

    def reserve(self, request: Request) -> None:
        # A throttler-aware scheduler reserves every request before handing it
        # to the engine, so acquire() always returns early for it and never
        # gets to evict idle scopes; do it here so their managers do not pile
        # up on broad crawls.
        self._maybe_evict(time.monotonic())
        managers = [
            (self.get_scope_manager(scope_id), quota_amount)
            for scope_id, quota_amount in self._cached_scope_quota_amounts(request)
        ]
        self._record_reservation(request, managers)

    def get_time_until_ready(self, request: Request) -> float | None:
        now = time.monotonic()
        wait = max(0.0, self._request_delay_deadline(request, now) - now)
        for scope_id, quota_amount in self._cached_scope_quota_amounts(request):
            manager = self.get_scope_manager(scope_id)
            wait = max(wait, manager.can_send(now=now, quota_amount=quota_amount))
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
        pairs = [(manager, manager.slot_available_event()) for manager in managers]
        events = [event for _, event in pairs]
        _, pending = await wait_for_first(events, timeout=_SLOT_WAIT_TIMEOUT)
        for manager, event in pairs:
            if event in pending:
                manager.discard_slot_available_event(event)

    async def _delay_request(self, request: Request) -> None:
        """Honor the :reqmeta:`delay` meta key by holding *request* for the
        requested number of seconds the first time it is processed.

        This is the blocking (:meth:`acquire`) counterpart of
        :meth:`_request_delay_deadline`, which the readiness API polls instead.
        """
        now = time.monotonic()
        wait = self._request_delay_deadline(request, now) - now
        if wait <= 0:
            return
        await sleep(wait)
        request.meta["_throttler_delayed"] = True

    def _request_delay_deadline(self, request: Request, now: float) -> float:
        """Return the monotonic time before which *request* must not be sent due
        to its :reqmeta:`delay`, or ``0.0`` if it has none.

        This is the readiness-API counterpart of :meth:`_delay_request`: a
        throttler-aware scheduler holds the request back until this deadline
        instead of awaiting :meth:`acquire`. The deadline is computed once, the
        first time the request reaches the gate, and stored so later polls reuse
        it. A request whose delay was already honored (the ``_throttler_delayed``
        flag) is never delayed again, so a resumed crawl does not re-block on a
        stale deadline."""
        delay = request.meta.get("delay")
        if not delay or request.meta.get("_throttler_delayed"):
            return 0.0
        deadline = request.meta.get("_throttler_delay_deadline")
        if deadline is None:
            deadline = now + float(delay)
            request.meta["_throttler_delay_deadline"] = deadline
            if self._debug:
                logger.debug(f"Holding {request} for {delay:.2f}s (delay)")
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
        host that *request* targets via :meth:`_apply_robots_crawl_delay`.
        """
        if not self._robotstxt_obey:
            return
        useragent: str | bytes = self._robotstxt_useragent or self._default_useragent
        try:
            delay = robotparser.crawl_delay(useragent)
        except Exception:  # pragma: no cover - backend-specific failures
            return
        if delay:
            self._apply_robots_crawl_delay(
                urlparse_cached(request).hostname or "", delay
            )

    def _apply_robots_crawl_delay(self, scope_id: ScopeID, delay: float) -> None:
        if not self._robotstxt_obey:
            return
        capped = min(delay, self._robotstxt_max_delay)
        config = self._scopes_config.get(scope_id, {})
        if config.get("ignore_robots_txt"):
            return
        if config.get("delay") is not None and float(config["delay"]) < capped:
            logger.warning(
                f"Throttling scope {scope_id!r} is configured with "
                f"delay={config['delay']!r}, which is more aggressive than its "
                f"robots.txt Crawl-delay of {capped}s. The configured value takes "
                "precedence; set 'ignore_robots_txt': True in its THROTTLING_SCOPES "
                "entry to silence this warning."
            )
            return
        if self._debug:
            logger.debug(f"robots.txt Crawl-delay for scope {scope_id}: {capped}s")
        self.get_scope_manager(scope_id).set_base_delay(capped)

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

    An instance manages one throttling scope's run-time throttling state: its
    delay and concurrency limits, its quota, and any gradual :ref:`backoff
    <backoff>`.

    Instances are built with :func:`~scrapy.utils.misc.build_from_crawler`,
    which passes the :class:`~scrapy.crawler.Crawler` and a ``config`` dict with
    the base configuration of the managed throttling scope. For example:

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
                "max_delay": 180.0,
            },
        }

    """

    def can_send(
        self, now: float | None = None, quota_amount: QuotaAmount | None = None
    ) -> float:
        """Return the number of seconds to wait before a request for this scope
        may be sent, or ``0`` if it may be sent right away.

        *quota_amount* is the expected :ref:`throttler quota
        <throttling-quotas>` consumption of the request, if any.
        """

    def record_sent(
        self, now: float | None = None, quota_amount: QuotaAmount | None = None
    ) -> None:
        """Record that a request for this scope has just been sent, consuming
        *quota_amount* of its :ref:`throttler quota <throttling-quotas>` if
        given."""

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
        ``Retry-After`` header). When omitted, a backoff step is applied
        instead.

        *cap* limits *delay* to :setting:`BACKOFF_MAX_DELAY`. It is ``True`` for
        untrusted input such as response headers, and may be set to ``False``
        for trusted, programmatic delays (see
        :meth:`ThrottlerProtocol.back_off`).
        """

    def reconcile_quota(
        self,
        consumed: float | None = None,
        remaining: float | None = None,
        now: float | None = None,
    ) -> None:
        """Reconcile the :ref:`throttler quota <throttling-quotas>` of this
        scope with the actual *consumed* amount (or the *remaining* amount)
        reported for a request, correcting the estimate used by
        :meth:`record_sent`."""

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

        :class:`Throttler` calls this (after all time-based gates in
        :meth:`can_send` are open) to decide whether to wait for a freed slot.
        Return ``False`` when no concurrency limit is enforced.
        """

    def get_load(self) -> float:
        """Return the current load of this scope: a non-negative number, with
        ``1.0`` meaning "as busy as its concurrency limit allows".

        A :ref:`throttler-aware scheduler <throttler-aware-scheduler>` uses
        this to break ties between equally-prioritized requests, preferring the
        least-loaded scopes. The reference implementation returns active sends
        divided by the concurrency limit (falling back to
        :setting:`CONCURRENT_REQUESTS` when the scope enforces no explicit
        limit), but any consistent busyness metric works; return ``0.0`` when
        none is meaningful.
        """

    def slot_available_event(self) -> Deferred[None]:
        """Return a :class:`~twisted.internet.defer.Deferred` that fires when
        a concurrency slot next becomes available (e.g. when
        :meth:`record_done` is called or the limit is raised via
        :meth:`set_concurrency`)."""

    def discard_slot_available_event(self, event: Deferred[None]) -> None:
        """Cancel a pending event returned by :meth:`slot_available_event`.

        Called by :class:`Throttler` when the wait ends without the
        event firing (e.g. another scope's slot opened first).
        """

    def is_idle(self, now: float, max_idle: float) -> bool:
        """Return whether this scope can be evicted from memory.

        A scope is idle when it has not been used for *max_idle* seconds and is
        not currently in an active (future) backoff.
        """


# Safety timeout for acquire() while it waits, event-driven, for a concurrency
# slot to free up: a slot_available_event normally fires first (from record_done() or
# set_concurrency()); this only guards against a request that never reaches
# release() so the wait can never hang forever.
_SLOT_WAIT_TIMEOUT = 1.0

# Internal tuning of the backoff algorithm, hardcoded rather than exposed as
# settings. _BACKOFF_MIN_DELAY must stay positive: it seeds the exponential
# when the base delay is 0 (a 0 seed would pin the delay at 0 forever).
_BACKOFF_DELAY_FACTOR = 2.0
_BACKOFF_JITTER = 0.1
_BACKOFF_MIN_DELAY = 1.0
_BACKOFF_WINDOW = 60.0


class ThrottlingScopeManager:
    r"""The default :setting:`THROTTLING_SCOPE_MANAGER` class.

    It implements a per-scope state machine covering delay, exponential
    :ref:`backoff <backoff>`, concurrency and :ref:`quotas
    <throttling-quotas>`:

    -   A base delay (the scope ``"delay"`` config, defaulting to
        :setting:`DOWNLOAD_DELAY`) is enforced between consecutive requests for
        the scope.

    -   On a backoff trigger the delay grows (see :meth:`record_backoff`); after
        quiet recovery windows it recovers (see :meth:`_recover`). The
        :ref:`backoff docs <backoff>` describe the algorithm. Backoff can be
        turned off for a scope with the ``"backoff"`` config's ``"enabled"``
        key, leaving it to rely solely on its delay and quota.

    -   When the scope is configured with a ``"concurrency"`` limit, no more
        than that many requests are allowed in flight at once.

    -   When the scope is configured with a ``"quota"``, no more than that much
        quota is consumed per ``"window"`` (default: :setting:`THROTTLER_WINDOW`).
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler, config: dict[str, Any]) -> Self:
        return cls(crawler, config)

    def __init__(self, crawler: Crawler, config: dict[str, Any]) -> None:
        settings = crawler.settings
        backoff: dict[str, Any] = config.get("backoff", {})
        self._id: ScopeID = config.get("id", "")
        self._backoff_enabled: bool = backoff.get("enabled", True)
        # The per-scope delay defaults to DOWNLOAD_DELAY; a scope can override
        # it with its own "delay" config (see THROTTLING_SCOPES).
        self._base_delay: float = float(
            config.get("delay", settings.getfloat("DOWNLOAD_DELAY"))
        )
        # Magnitude of the random variation applied to the (non-backoff) delay,
        # normalized to a (low, high) multiplier range (or None for no jitter).
        # Defaults to RANDOMIZE_DOWNLOAD_DELAY's historical ±50% when delay
        # randomization is on, or to no variation when it is off.
        self._jitter: JitterRange | None = self._normalize_jitter(
            config.get(
                "jitter", 0.5 if settings.getbool("RANDOMIZE_DOWNLOAD_DELAY") else 0.0
            )
        )
        self._delay_factor: float = _BACKOFF_DELAY_FACTOR
        self._max_delay: float = float(
            backoff.get("max_delay", settings.getfloat("BACKOFF_MAX_DELAY"))
        )
        self._min_delay: float = _BACKOFF_MIN_DELAY
        self._backoff_jitter: JitterRange | None = self._normalize_jitter(
            _BACKOFF_JITTER
        )
        # Which responses/exceptions trigger backoff is decided by the backoff
        # middleware (see BackoffMiddleware), which reads the same per-scope
        # "http_codes"/"exceptions" config and the global BACKOFF_* settings.
        self._window: float = _BACKOFF_WINDOW

        # Concurrency. ``None`` means no scope-level limit (the downloader slots
        # enforce concurrency instead); a limit is only set when configured
        # explicitly.
        configured_concurrency = config.get("concurrency")
        if configured_concurrency is not None:
            self._concurrency: int | None = int(configured_concurrency)
        else:
            self._concurrency = _default_scope_concurrency(settings) or None
        # Used as the load denominator when the scope enforces no explicit
        # concurrency limit (see get_load()).
        self._global_concurrency: int = settings.getint("CONCURRENT_REQUESTS")

        # Quota.
        quota = config.get("quota")
        self._quota: QuotaAmount | None = None if quota is None else float(quota)
        self._quota_window: float = float(
            config.get("window", settings.getfloat("THROTTLER_WINDOW"))
        )

        # State.
        self._delay: float = self._base_delay
        # Bracket for the recovery search (see _recover): highest delay known to
        # trigger, lowest known safe. None until observed.
        self._max_unsafe: float | None = None
        self._min_safe: float | None = None
        self._next_allowed_time: float | None = None
        self._in_backoff_until: float | None = None
        self._last_backoff_time: float | None = None
        self._last_seen: float | None = None
        self._active: int = 0
        self._slot_waiters: list[Deferred[None]] = []
        self._consumed: float = 0.0
        self._quota_window_start: float | None = None

    @staticmethod
    def _now(now: float | None) -> float:
        return time.monotonic() if now is None else now

    @staticmethod
    def _normalize_jitter(
        jitter: float | list[float],
    ) -> JitterRange | None:
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
    def _apply_jitter(value: float, jitter: JitterRange | None) -> float:
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
        jitter = (
            self._backoff_jitter if self._delay > self._base_delay else self._jitter
        )
        return self._apply_jitter(self._delay, jitter)

    def _recover(self, now: float) -> None:
        # Bracketing search for the smallest tolerated delay, one recovery
        # window per step; see the "backoff" docs for the algorithm.
        if self._last_backoff_time is None or self._delay <= self._base_delay:
            return
        while now - self._last_backoff_time >= self._window:
            self._last_backoff_time += self._window
            self._recover_step()
            if self._delay - self._base_delay < self._min_delay:
                self._reset_backoff()  # within one step of base: fully recovered
                return

    def _recover_step(self) -> None:
        current = self._delay
        # A full quiet window proves the current delay safe; probe halfway down
        # toward _max_unsafe (or the base delay) to look for a smaller one.
        self._min_safe = (
            current if self._min_safe is None else min(self._min_safe, current)
        )
        lower = self._base_delay if self._max_unsafe is None else self._max_unsafe
        self._delay = max(self._base_delay, (lower + self._min_safe) / 2)
        # Decay _max_unsafe toward base so probing can descend past a stale bound
        # and track a server that became more permissive.
        if self._max_unsafe is not None:
            self._max_unsafe = (self._base_delay + self._max_unsafe) / 2
            if self._max_unsafe - self._base_delay < self._min_delay:
                self._max_unsafe = None

    def _reset_backoff(self) -> None:
        """Return the scope to its non-backoff steady state."""
        self._delay = self._base_delay
        self._max_unsafe = None
        self._min_safe = None
        self._in_backoff_until = None
        self._last_backoff_time = None

    def _maybe_reset_quota(self, now: float) -> None:
        if self._quota is None:
            return
        if self._quota_window <= 0:
            # No window: no reset cadence to step (would spin); keep it reset.
            self._consumed = 0.0
            self._quota_window_start = now
            return
        if self._quota_window_start is None:
            self._quota_window_start = now
            return
        while now - self._quota_window_start >= self._quota_window:
            self._quota_window_start += self._quota_window
            self._consumed = 0.0

    def can_send(
        self, now: float | None = None, quota_amount: QuotaAmount | None = None
    ) -> float:
        # can_send() only refreshes passive, time-based state (backoff recovery
        # and the quota window) to reflect the current time.
        now = self._now(now)
        self._recover(now)
        self._maybe_reset_quota(now)
        waits = [0.0]
        if self._in_backoff_until is not None:
            waits.append(self._in_backoff_until - now)
        if self._next_allowed_time is not None:
            waits.append(self._next_allowed_time - now)
        if self._quota is not None:
            need = 0.0 if quota_amount is None else float(quota_amount)
            # Block until the window resets only if some quota is already spent;
            # a single oversized request is always allowed through.
            if self._consumed > 0 and self._consumed + need > self._quota:
                start = self._quota_window_start or now
                waits.append(start + self._quota_window - now)
        # Concurrency is enforced separately, via concurrency_blocked() and
        # slot_available_event(), so acquire() can wait for a freed slot without
        # polling.
        return max(waits)

    def record_sent(
        self, now: float | None = None, quota_amount: QuotaAmount | None = None
    ) -> None:
        now = self._now(now)
        self._last_seen = now
        if self._in_backoff_until is not None and now >= self._in_backoff_until:
            self._in_backoff_until = None
        self._next_allowed_time = now + self._effective_delay()
        self._active += 1
        if self._quota is not None and quota_amount is not None:
            self._maybe_reset_quota(now)
            self._consumed += float(quota_amount)

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

    def slot_available_event(self) -> Deferred[None]:
        event: Deferred[None] = Deferred()
        self._slot_waiters.append(event)
        return event

    def discard_slot_available_event(self, event: Deferred[None]) -> None:
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
        if not self._backoff_enabled:
            return
        now = self._now(now)
        self._last_seen = now
        self._last_backoff_time = now
        if delay is not None:
            # A hard delay (e.g. Retry-After) is a one-time gate, not the
            # steady-state delay; the exponential step below still applies.
            hard = min(float(delay), self._max_delay) if cap else float(delay)
            self._in_backoff_until = now + hard
        # The current delay just triggered: it is the new lower bound of the
        # recovery search (see _recover).
        self._max_unsafe = (
            self._delay
            if self._max_unsafe is None
            else max(self._max_unsafe, self._delay)
        )
        if self._min_safe is not None and self._min_safe <= self._max_unsafe:
            self._min_safe = None  # stale (server got stricter): rediscover it
        if self._min_safe is not None:
            # Jump straight back to the known-safe delay; recovery only probes
            # below it, so triggering stops at once instead of creeping up.
            grown = self._min_safe
        else:
            # No safe delay known yet: grow exponentially to find one.
            grown = (
                self._delay * self._delay_factor if self._delay > 0 else self._min_delay
            )
        # Deterministic, bounded delay; jitter is applied per use in
        # _effective_delay() so it does not compound across steps.
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

    def get_base_delay(self) -> float:
        return self._base_delay

    def set_base_delay(self, delay: float, *, only_increase: bool = True) -> None:
        if only_increase and delay <= self._base_delay:
            return
        # Whether a backoff is currently raising the delay above the base must
        # be checked before the base changes.
        backing_off = self._delay > self._base_delay
        self._base_delay = delay
        # Reflect the change in the effective delay unless a backoff is raising
        # it above the base right now.
        if not backing_off:
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
