from __future__ import annotations

import json
import logging
import random
import time
import warnings
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Mapping
from functools import wraps
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, TypeVar, cast
from weakref import WeakKeyDictionary, WeakSet

from typing_extensions import Self

from scrapy import signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import SETTINGS_PRIORITIES
from scrapy.utils.asyncio import sleep, wait_for_first
from scrapy.utils.defer import _Event
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred

    from scrapy.core.downloader import Downloader
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
    """Per-scope override of :setting:`THROTTLING_SCOPE_CONCURRENCY`. Must be
    ``1`` or higher: a scope always enforces a concurrency limit."""

    delay: float
    """Per-scope override of :setting:`DOWNLOAD_DELAY`."""

    jitter: float
    """Magnitude of the random variation applied to ``delay``; the per-scope
    override of :setting:`RANDOMIZE_DOWNLOAD_DELAY` (``0`` disables it, ``0.5``
    means ±50%)."""

    quota: float
    """Maximum :ref:`throttler quota <throttler-quotas>` the scope may consume
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
RequestScopes = None | ScopeID | Iterable[ScopeID] | ScopeQuotas
if TYPE_CHECKING:
    # A scope of a request being throttled: its ID, its manager, and the quota
    # amount the request consumes from it.
    ScopeSlot = tuple[ScopeID, "ThrottlingScopeManagerProtocol", QuotaAmount | None]


def iter_scopes(scopes: RequestScopes) -> Iterable[ScopeID]:
    """Iterate over the scope IDs of *scopes*, whatever its form.

    :class:`~ThrottlerProtocol.get_scopes` (and
    :meth:`~ThrottlerProtocol.get_resolved_scopes`) may return a single
    scope ID, an iterable of them, a ``{scope_id: quota}`` mapping, or ``None``;
    this helper normalizes any of those into an iterable of scope IDs, e.g. to
    react to a request's scopes in a custom middleware.
    """
    return (scope for scope, _ in _iter_scope_quota_amounts(scopes))


def _iter_scope_quota_amounts(
    scopes: RequestScopes,
) -> Iterable[tuple[ScopeID, QuotaAmount | None]]:
    """Iterate over *scopes* as ``(scope_id, quota_amount)`` pairs, using
    ``None`` as the quota amount of scopes that have none."""
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


def _default_scope_concurrency_setting(settings: BaseSettings) -> str:
    """Return the name of the setting that defines the concurrency of a
    throttling scope that does not set its own ``concurrency``:
    :setting:`THROTTLING_SCOPE_CONCURRENCY`, or the deprecated
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` when set at a higher
    :ref:`priority <populating-settings>` or when neither is set (see
    :func:`_warn_on_deprecated_concurrency`)."""
    domain_priority = _effective_priority(settings, "CONCURRENT_REQUESTS_PER_DOMAIN")
    scope_priority = _effective_priority(settings, "THROTTLING_SCOPE_CONCURRENCY")
    if domain_priority > scope_priority or (
        domain_priority == scope_priority
        and domain_priority <= SETTINGS_PRIORITIES["default"]
    ):
        return "CONCURRENT_REQUESTS_PER_DOMAIN"
    return "THROTTLING_SCOPE_CONCURRENCY"


def _default_scope_concurrency(settings: BaseSettings) -> int:
    """Return the default concurrency of a throttling scope that does not set
    its own ``concurrency``, i.e. the value of the setting chosen by
    :func:`_default_scope_concurrency_setting`."""
    return settings.getint(_default_scope_concurrency_setting(settings))


def _warn_on_deprecated_concurrency(settings: BaseSettings) -> None:
    """Warn about the concurrency settings bridged by
    :func:`_default_scope_concurrency`: that
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` is deprecated when it is set, and
    that its default is still what applies when neither setting is. Call once
    per crawl (see :meth:`Throttler.__init__`)."""
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


def _check_scope_config(setting: str, scope_id: str, config: Any) -> Mapping[str, Any]:
    """Return *config* if it is a per-scope mapping, or raise a
    :exc:`TypeError` naming the offending entry, rather than let it fail as
    something less telling deeper in."""
    if not isinstance(config, Mapping):
        raise TypeError(
            f"{setting}[{scope_id!r}] must be a mapping of configuration keys "
            f"to values, got {config!r}."
        )
    return config


def _warn_on_unachievable_concurrency(
    settings: BaseSettings, scopes_config: dict[str, dict[str, Any]]
) -> None:
    """Warn about per-scope concurrency limits in *scopes_config* that exceed
    :setting:`CONCURRENT_REQUESTS`, and hence can never be reached. Call once
    per crawl (see :meth:`Throttler.__init__`).

    A :setting:`CONCURRENT_REQUESTS` of ``0`` caps nothing. Of the two settings
    that can define the default per-scope concurrency, only the one in effect is
    reported, so that a deprecated setting the user never set is not named as an
    offender.
    """
    global_concurrency = settings.getint("CONCURRENT_REQUESTS")
    if not global_concurrency:
        return
    offenders: list[str] = []
    default_name = _default_scope_concurrency_setting(settings)
    default_concurrency = settings.getint(default_name)
    if default_concurrency > global_concurrency:
        offenders.append(f"{default_name}={default_concurrency}")
    offenders += [
        f"the concurrency of throttling scope {scope_id!r}={config['concurrency']}"
        for scope_id, config in scopes_config.items()
        if config.get("concurrency") is not None
        and int(config["concurrency"]) > global_concurrency
    ]
    if offenders:
        logger.warning(
            f"The following concurrency settings exceed CONCURRENT_REQUESTS "
            f"({global_concurrency}), which caps the total number of requests in "
            f"flight, so they cannot be reached: {', '.join(offenders)}."
        )


def _check_scope_concurrency(
    settings: BaseSettings, scopes_config: dict[str, dict[str, Any]]
) -> None:
    """Reject non-positive throttling scope concurrency limits, which would
    leave a scope with no slot to give and hold its requests back forever. Call
    once per crawl (see :meth:`Throttler.__init__`)."""
    name = _default_scope_concurrency_setting(settings)
    concurrency = settings.getint(name)
    if concurrency < 1:
        raise ValueError(f"{name} must be 1 or higher, got {concurrency!r}.")
    for scope_id, config in scopes_config.items():
        if config.get("concurrency") is None:
            continue
        concurrency = int(config["concurrency"])
        if concurrency < 1:
            raise ValueError(
                f"The concurrency of throttling scope {scope_id!r} must be 1 or "
                f"higher, got {concurrency!r}."
            )


def add_scope(
    scopes: RequestScopes,
    scope: ScopeID,
    quota_amount: QuotaAmount | None = None,
    /,
) -> ScopeQuotas:
    """Add *scope* to *scopes* with *quota_amount*, returning a new
    ``{scope_id: quota}`` dict and leaving *scopes* untouched.

    This is a utility function to help extending the output of
    :meth:`~ThrottlerProtocol.get_scopes`, e.g. in
    :class:`Throttler` subclasses.

    Adding a scope with a *quota_amount* fails if it is already present, so an
    existing :ref:`quota <throttler-quotas>` is never silently overwritten;
    adding it without a quota amount leaves any existing entry untouched.
    """
    if scopes is not None and not isinstance(scopes, (str, dict, Iterable)):
        raise TypeError(
            f"Invalid type ({type(scopes)}) of scopes value "
            f"{scopes!r}. Expected None, str, Iterable or dict."
        )
    # A new dict, so that the caller's (for the scopes of a request, the one
    # persisted on request.meta; see scope_cache) is never modified.
    result = dict(_iter_scope_quota_amounts(scopes))
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
        keys and :ref:`throttler quotas <throttler-quotas>` as values.
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

    async def acquire(self, request: Request, *, unscheduled: bool = False) -> None:
        """Block until *request* is allowed to be sent by all of its scopes.

        The engine awaits this before handing a request to the downloader.

        *unscheduled* tells whether *request* was sent without going through the
        scheduler, i.e. through :meth:`crawler.engine.download_async()
        <scrapy.core.engine.ExecutionEngine.download_async>`. Such a request may
        be a prerequisite of a request that holds a concurrency slot of the same
        scope while it waits for it, as the built-in robots.txt middleware does,
        so an implementation must make sure it can never be blocked by such a
        request forever.

        A request with the :reqmeta:`dont_throttle` metadata key is not held by
        its scopes and does not count towards them; only its own
        :reqmeta:`delay`, if any, still applies. The same goes for
        :meth:`is_ready`, :meth:`reserve` and :meth:`get_time_until_ready`.
        """

    def release(self, request: Request) -> None:
        """Release the concurrency slots that :meth:`acquire` reserved for
        *request*.

        The engine calls this once *request* has finished downloading (whether
        it succeeded, failed or returned a new request), so that scopes that
        enforce a concurrency limit can let other requests through.
        """

    def download_handler_blocked(self, request: Request) -> bool:
        """Return whether sending *request* right now would put more requests of
        one of its scopes in a download handler at once than that scope's
        concurrency allows.

        The downloader asks this just before handing *request* to a download
        handler, so that the leeway :meth:`acquire` hands out to unscheduled
        requests cannot let a scope exceed its concurrency where it counts. An
        implementation that hands out no such leeway can always return ``False``.

        A blocked request is retried as requests leave their download handler,
        so an implementation must only block on requests that are in one, which
        end on their own.
        """

    def is_ready(self, request: Request) -> bool:
        """Return whether every scope of *request* allows it to be sent right
        now, i.e. every time-based limit (delay, backoff, quota window) has
        elapsed *and* a concurrency slot is free in every scope.

        This is the synchronous, non-blocking counterpart of :meth:`acquire`,
        used by a :ref:`throttler-aware scheduler
        <throttler-aware-scheduler>` to decide whether a request can be
        dequeued now. It assumes the scopes of *request* have already been
        resolved (e.g. by an earlier :meth:`get_scopes` call at enqueue time).

        It also returns ``False`` when a free slot of one of the scopes of
        *request* is claimed by an unscheduled request waiting in
        :meth:`acquire`, which gets it first.
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
        """Return the number of seconds until every time-based limit of
        *request* would have elapsed, or ``None`` if no time-based limit is
        currently blocking it (only a concurrency slot could be).

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
        active sends divided by its concurrency limit, which a
        :ref:`throttler-aware scheduler <throttler-aware-scheduler>` uses to
        prefer the least-loaded scopes when dequeuing.

        It can exceed ``1.0``: lending an unused slot (see the *unscheduled*
        argument of :meth:`acquire`) makes the outstanding sends of a scope
        outnumber its concurrency until the borrowers drain.

        A scope with no throttling state yet has a load of ``0.0``.
        Implementations should not create state just to answer this: it is
        called for every queued scope on every dequeue.
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
        least *delay* seconds before its next request: a one-time hold (e.g.
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
        """Reconcile the :ref:`throttler quota <throttler-quotas>` of each of
        *scopes* with an actually *consumed* amount (a delta to add) or a
        *remaining* amount (an absolute value), correcting the estimate used
        when requests were sent.

        Like :meth:`back_off`, this is meant to be called from a downloader
        middleware or spider callback that learns the real quota cost of a
        request from its response.
        """

    def get_scope_manager(self, scope_id: str) -> ThrottlingScopeManagerProtocol:
        """Return the :class:`ThrottlingScopeManagerProtocol` instance handling
        the scope identified by *scope_id*, creating it if necessary.

        Use it to read or drive the state of a scope directly, e.g. to set its
        delay with
        :meth:`~ThrottlingScopeManagerProtocol.set_base_delay`."""


_GetScopesMethod = TypeVar(
    "_GetScopesMethod", bound=Callable[..., Awaitable[RequestScopes]]
)


# Request.meta key under which scope_cache persists the resolved scopes so that
# they survive a request being serialized to and restored from a disk queue.
_RESOLVED_SCOPES_META_KEY = "_throttler_resolved_scopes"

# Request.meta key under which the downloader records the 'download_slot' value
# it set itself (see Downloader._enqueue_request), so that the deprecation of
# that meta key is only reported for values that a user set; see
# Throttler._resolve_scopes_sync.
_STAMPED_SLOT_META_KEY = "_throttler_stamped_download_slot"

# Request.meta keys tracking the state of the 'delay' meta key: whether it has
# been honored already, and the deadline it set (see
# Throttler._request_delay_deadline).
_DELAYED_META_KEY = "_throttler_delayed"
_DELAY_DEADLINE_META_KEY = "_throttler_delay_deadline"


def _set_request_delay(request: Request, delay: float) -> None:
    """Hold *request* back for *delay* seconds through the :reqmeta:`delay` meta
    key, dropping the state of any delay it inherited from the request it
    derives from (e.g. through :meth:`Request.replace() <scrapy.Request.replace>`,
    which copies ``meta``)."""
    request.meta["delay"] = delay
    request.meta.pop(_DELAYED_META_KEY, None)
    request.meta.pop(_DELAY_DEADLINE_META_KEY, None)


def _mark_request_delayed(request: Request) -> None:
    """Record that the :reqmeta:`delay` of *request* has been honored, so that it
    is not delayed again, e.g. on resuming a crawl."""
    request.meta[_DELAYED_META_KEY] = True


def scope_cache(f: _GetScopesMethod) -> _GetScopesMethod:
    """Decorator for :meth:`~ThrottlerProtocol.get_scopes`
    implementations that persists the resolved scopes on ``request.meta``.

    The readers of the resolved scopes — the synchronous readiness API of a
    :ref:`throttler-aware scheduler <throttler-aware-scheduler>` and
    :meth:`~ThrottlerProtocol.get_resolved_scopes` — read this persisted value
    instead of resolving the scopes again, so they stay cheap and consistent,
    and it survives a request being serialized to and restored from a
    :ref:`disk queue <topics-jobs>`.

    The decorated method always re-resolves, so a request that inherited
    ``request.meta`` from another one (e.g. a redirect built with
    :meth:`Request.replace() <scrapy.Request.replace>`, which copies ``meta``)
    overwrites the inherited scopes with its own.

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

    Subclass it and override :meth:`get_default_scopes` to assign scopes
    differently.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def __init__(self, crawler: Crawler) -> None:
        self.crawler = crawler
        # Merged (and shape-checked) first, so that a malformed per-scope entry
        # is reported as such instead of blowing up inside a warning helper.
        self._scopes_config: dict[str, dict[str, Any]] = self._merge_download_slots(
            crawler.settings
        )
        _check_scope_concurrency(crawler.settings, self._scopes_config)
        _warn_on_deprecated_concurrency(crawler.settings)
        _warn_on_unachievable_concurrency(crawler.settings, self._scopes_config)
        self._debug = crawler.settings.getbool("THROTTLER_DEBUG")
        self._robotstxt_obey = crawler.settings.getbool(
            "ROBOTSTXT_OBEY"
        ) and crawler.settings.getbool("THROTTLER_ROBOTSTXT_OBEY")
        self._robotstxt_max_delay = crawler.settings.getfloat(
            "THROTTLER_ROBOTSTXT_MAX_DELAY"
        )
        self._default_useragent: str = crawler.settings["USER_AGENT"]
        self._robotstxt_useragent: str | None = crawler.settings["ROBOTSTXT_USER_AGENT"]
        self._robotstxt_scope_warned: bool = False
        if self._robotstxt_obey:
            crawler.signals.connect(
                self._on_robots_parsed, signal=signals.robots_parsed
            )
        self._default_scope_manager_cls = load_object(
            crawler.settings["THROTTLING_SCOPE_MANAGER"]
        )
        # Ordered by least-recently-used first (see get_scope_manager), so the
        # scope limit can evict the coldest idle scopes (see THROTTLING_SCOPE_LIMIT).
        self._scope_managers: OrderedDict[ScopeID, ThrottlingScopeManagerProtocol] = (
            OrderedDict()
        )
        self._scope_limit: int = crawler.settings.getint("THROTTLING_SCOPE_LIMIT")
        # Scopes whose managers are being resolved together for one request, and
        # which the scope limit must therefore not evict; see
        # _resolve_scope_slots().
        self._resolving: set[ScopeID] = set()
        # Concurrency slots reserved by acquire(), to be released once the
        # request finishes downloading.
        self._reserved: WeakKeyDictionary[Request, list[ScopeSlot]] = (
            WeakKeyDictionary()
        )
        # Requests holding a reserved slot of each scope, i.e. the reverse of
        # _reserved, used to tell whether a scope can lend a slot to an
        # unscheduled request (see _can_lend_slot).
        self._scope_holders: dict[ScopeID, WeakSet[Request]] = {}
        # Unscheduled requests currently waiting in acquire(), by scope, so that
        # a slot freed in one of those scopes goes to them before it goes to a
        # request from the scheduler (see _unscheduled_claims).
        self._unscheduled_waiters: dict[ScopeID, WeakSet[Request]] = {}

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

        Entry shapes are checked here, so that everything downstream can assume
        a mapping per scope rather than failing on a malformed one somewhere
        further in.
        """
        scopes: dict[str, dict[str, Any]] = {
            scope_id: dict(_check_scope_config("THROTTLING_SCOPES", scope_id, config))
            for scope_id, config in settings.getdict("THROTTLING_SCOPES").items()
        }
        for slot_id, slot_config in settings.getdict("DOWNLOAD_SLOTS").items():
            _check_scope_config("DOWNLOAD_SLOTS", slot_id, slot_config)
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

    def get_default_scopes(self, request: Request) -> RequestScopes:
        """Return the :ref:`throttling scopes <throttling-scopes>` of *request*
        when it does not choose its own through the :reqmeta:`throttling_scopes`
        metadata key: its host name.

        This is the extension point to prefer for custom scoping: everything
        that needs the scopes of a request goes through it, including the
        synchronous :meth:`~ThrottlerProtocol.get_scopes_key`, which is what the
        :ref:`scheduler <topics-scheduler>` groups queued requests by. Override
        :meth:`~ThrottlerProtocol.get_scopes` only for scoping that needs
        ``await``; see :ref:`custom-throttling-scopes`.
        """
        return urlparse_cached(request).hostname or ""

    def _resolve_scopes_sync(self, request: Request) -> RequestScopes:
        """Best-effort synchronous scope resolution: the
        :reqmeta:`throttling_scopes` metadata key if the request sets one, and
        otherwise :meth:`get_default_scopes`.

        It backs :meth:`get_scopes` and :meth:`get_scopes_key`, and is also the
        fallback for the synchronous readiness methods when no scopes were
        persisted on ``request.meta`` by an earlier :meth:`get_scopes` call (see
        :func:`scope_cache`).
        """
        scopes = request.meta.get("throttling_scopes")
        if scopes is not None:
            return cast("RequestScopes", scopes)
        download_slot = request.meta.get("download_slot")
        # A value the downloader stamped (see Downloader._enqueue_request) is
        # bookkeeping rather than intent: honoring the one a derived request
        # (a redirect, a retry) inherits would keep it in the scope of a
        # different host. Anything else is a user's choice of scope.
        if download_slot is not None and download_slot != request.meta.get(
            _STAMPED_SLOT_META_KEY
        ):
            warnings.warn(
                "The 'download_slot' request meta key is deprecated. Use "
                "'throttling_scopes' instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
            return cast("RequestScopes", download_slot)
        return self.get_default_scopes(request)

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
        scopes = self.get_resolved_scopes(request)
        # The readiness API asks for this on every queued scope set on every
        # dequeue, and default scoping yields a single, quota-less scope;
        # skipping the general iteration there measures 2.3x faster.
        if isinstance(scopes, str):
            return [(scopes, None)]
        return list(_iter_scope_quota_amounts(scopes))

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

    def _resolve_scope_slots(
        self, scope_values: list[tuple[ScopeID, QuotaAmount | None]]
    ) -> list[ScopeSlot]:
        """Return the ``ScopeSlot`` of every entry of *scope_values*.

        Resolved together, and marked as such in :attr:`_resolving`, because
        :meth:`get_scope_manager` enforces :setting:`THROTTLING_SCOPE_LIMIT` as
        soon as it creates a manager and only spares the scope it created:
        one at a time, a scope of this request could evict another one.
        """
        self._resolving.update(scope_id for scope_id, _ in scope_values)
        try:
            return [
                (scope_id, self.get_scope_manager(scope_id), quota_amount)
                for scope_id, quota_amount in scope_values
            ]
        finally:
            self._resolving.clear()

    def _live_scope_manager(
        self, scope_id: ScopeID
    ) -> ThrottlingScopeManagerProtocol | None:
        """Return the manager of *scope_id* if there already is one, without
        creating it and without marking it as recently used.

        A scope with no manager has no throttling state, so the readiness API
        reads ``None`` as "this scope allows the request through". That is what
        keeps it cheap enough to call for every queued scope set on every
        dequeue, and what keeps merely considering a scope from counting as
        using it in the LRU eviction order.
        """
        return self._scope_managers.get(scope_id)

    def _enforce_scope_limit(self, keep: ScopeID) -> None:
        """Evict least-recently-used idle scopes while the number of live scope
        managers exceeds :setting:`THROTTLING_SCOPE_LIMIT` (``0`` disables the
        limit).

        LRU order is kept by :meth:`get_scope_manager` moving each accessed
        scope to the end, so the coldest scopes are at the front. Only
        :meth:`~ThrottlingScopeManagerProtocol.is_idle` scopes are evicted, and
        never the just-created *keep* scope or the ones being resolved along with
        it (see :meth:`_resolve_scope_slots`). An evicted scope is recreated from
        its configuration the next time it is needed.
        """
        if self._scope_limit <= 0:
            return
        excess = len(self._scope_managers) - self._scope_limit
        if excess <= 0:
            return
        now = time.monotonic()
        evictable: list[ScopeID] = []
        for scope_id, manager in self._scope_managers.items():
            if len(evictable) >= excess:
                break
            if (
                scope_id != keep
                and scope_id not in self._resolving
                and manager.is_idle(now)
            ):
                evictable.append(scope_id)
        for scope_id in evictable:
            del self._scope_managers[scope_id]

    async def acquire(self, request: Request, *, unscheduled: bool = False) -> None:
        # A throttler-aware scheduler reserves the request before handing it
        # to the engine, so there is nothing left to wait for or record here.
        if request in self._reserved:
            return
        await self._delay_request(request)
        # The scopes are resolved (and persisted, see scope_cache) even for a
        # request excluded from throttling, because its outcome still backs off
        # its scopes, and get_resolved_scopes() is how a middleware finds them.
        scope_values = list(_iter_scope_quota_amounts(await self.get_scopes(request)))
        if request.meta.get("dont_throttle"):
            return
        if not scope_values:
            return
        if not unscheduled:
            await self._acquire_scope_slots(request, scope_values, unscheduled=False)
            return
        # A registration here holds back is_ready() for the whole scope (see
        # _unscheduled_claims), so one that outlived its wait would stall a
        # throttler-aware scheduler for good. The finally below covers every way
        # this coroutine can end, including being cancelled or abandoned (both
        # of which throw into the await).
        for scope_id, _ in scope_values:
            self._unscheduled_waiters.setdefault(scope_id, WeakSet()).add(request)
        try:
            await self._acquire_scope_slots(request, scope_values, unscheduled=True)
        finally:
            for scope_id, _ in scope_values:
                waiters = self._unscheduled_waiters.get(scope_id)
                if waiters is not None:
                    waiters.discard(request)
                    if not waiters:
                        del self._unscheduled_waiters[scope_id]

    async def _acquire_scope_slots(
        self,
        request: Request,
        scope_values: list[tuple[ScopeID, QuotaAmount | None]],
        *,
        unscheduled: bool,
    ) -> None:
        """Block until every scope in *scope_values* allows *request* through,
        then reserve a slot on each of them.

        The scope managers are resolved anew on every pass: a scope can be
        evicted while this waits (see :setting:`THROTTLING_SCOPE_LIMIT`), and
        recording the send on a replaced manager would leave the scope with two
        sets of counters, letting it exceed its limits.
        """
        scope_ids = [scope_id for scope_id, _ in scope_values]
        yielded_to_unscheduled = False
        while True:
            # Rechecked on every pass: a second send that only one release()
            # undoes would leave these scopes permanently short of a slot. It
            # takes an unsupported crawl (one Request object downloaded twice at
            # once) to get here.
            if request in self._reserved:
                return
            scopes = self._resolve_scope_slots(scope_values)
            wait = max(
                [
                    0.0,
                    *(
                        manager.can_send(quota_amount=quota_amount)
                        for _, manager, quota_amount in scopes
                    ),
                ]
            )
            if wait > 0:
                if self._debug:
                    logger.debug(
                        f"Throttling {request} for {wait:.2f}s (scopes: {scope_ids})"
                    )
                await sleep(wait)
                continue
            # Every time-based limit (delay, backoff, quota) has elapsed; the
            # only remaining reason to wait is a full concurrency slot.
            blocked = [
                (scope_id, manager)
                for scope_id, manager, _ in scopes
                if manager.concurrency_blocked()
            ]
            if not blocked:
                if (
                    not unscheduled
                    and not yielded_to_unscheduled
                    and self._unscheduled_claims(scope_ids)
                ):
                    # An unscheduled request waiting for one of these scopes can
                    # use the free slot right now, and something in flight may
                    # be waiting for it, so let it go first. Only once, so that
                    # a claim that no one takes cannot spin here.
                    yielded_to_unscheduled = True
                    await sleep(0)
                    continue
                self._record_reservation(request, scopes)
                return
            if unscheduled and all(
                self._can_lend_slot(scope_id) for scope_id, _ in blocked
            ):
                self._borrow_slots(
                    request, scopes, [scope_id for scope_id, _ in blocked]
                )
                return
            if self._debug:
                logger.debug(
                    f"Throttling {request} until a concurrency slot frees up "
                    f"(scopes: {scope_ids})"
                )
            await self._wait_for_slot(
                [manager for _, manager in blocked], unscheduled=unscheduled
            )

    def _record_reservation(self, request: Request, scopes: list[ScopeSlot]) -> None:
        """Record a send on each of *request*'s *scopes* and mark *request* as
        reserved, so :meth:`release` can later free the slots. This is the
        shared tail of :meth:`acquire` and :meth:`reserve`."""
        for scope_id, manager, quota_amount in scopes:
            manager.record_sent(quota_amount=quota_amount)
            self._scope_holders.setdefault(scope_id, WeakSet()).add(request)
        self._reserved[request] = scopes

    def release(self, request: Request) -> None:
        scopes = self._reserved.pop(request, None)
        if not scopes:
            return
        for scope_id, manager, _ in scopes:
            holders = self._scope_holders.get(scope_id)
            if holders is not None:
                holders.discard(request)
                if not holders:
                    del self._scope_holders[scope_id]
            manager.record_done()

    # -- Unscheduled requests ---------------------------------------------------

    def _downloader(self) -> Downloader | None:
        engine = self.crawler.engine
        return None if engine is None else engine.downloader

    def _in_downloader_middlewares(self, request: Request) -> bool:
        """Return whether the downloader middlewares are processing *request*,
        i.e. it holds a concurrency slot that it is not using, because it is in
        the downloader but no download handler is working on it."""
        downloader = self._downloader()
        return downloader is not None and downloader._in_downloader_middlewares(request)

    def _can_lend_slot(self, scope_id: ScopeID) -> bool:
        """Return whether *scope_id* can lend a concurrency slot to an
        unscheduled request: whether every request holding one of its slots is
        in the downloader middlewares, where it may be waiting for that very
        request, and where the slot it holds is going unused anyway.
        """
        # A borrower is itself such a holder while its own middlewares run, so
        # borrowing chains: outstanding reservations, and hence the load of the
        # scope, can exceed its concurrency until the borrowers drain.
        # download_handler_blocked() is what keeps that from reaching the
        # network.
        holders = self._scope_holders.get(scope_id)
        if not holders:
            return False
        return all(self._in_downloader_middlewares(holder) for holder in holders)

    def download_handler_blocked(self, request: Request) -> bool:
        # Nothing keeps a scope that lent a slot out (see _can_lend_slot) from
        # reaching a download handler again while the borrower is still in one.
        # This is what caps a scope at its concurrency where it counts.
        scopes = self._reserved.get(request)
        if not scopes:
            # No reservation to speak of: an unscoped or dont_throttle request.
            return False
        downloader = self._downloader()
        if downloader is None:
            return False
        in_download_handler = downloader._in_download_handler
        if not in_download_handler:
            return False
        for scope_id, manager, _ in scopes:
            holders = self._scope_holders.get(scope_id)
            if not holders:
                continue
            # *request* has not reached a handler yet, so it does not count
            # itself.
            in_handlers = sum(1 for holder in holders if holder in in_download_handler)
            if in_handlers >= manager.get_concurrency():
                if self._debug:
                    logger.debug(
                        f"Holding {request} off the network: scope {scope_id} "
                        f"already has {in_handlers} request(s) in a download handler"
                    )
                return True
        return False

    def _borrow_slots(
        self, request: Request, scopes: list[ScopeSlot], borrowed: list[ScopeID]
    ) -> None:
        """Reserve the *scopes* of *request*, borrowing an unused slot from each
        scope in *borrowed*, which has none free."""
        if self.crawler.stats:
            self.crawler.stats.inc_value("throttler/borrowed_slots")
        if self._debug:
            logger.debug(
                f"Letting {request} borrow a concurrency slot of every scope in "
                f"{borrowed}, whose slots are all held by requests that no "
                f"download handler is working on"
            )
        self._record_reservation(request, scopes)

    def _unscheduled_claims(self, scope_ids: list[ScopeID]) -> bool:
        """Return whether an unscheduled request waiting in :meth:`acquire`
        could use a free slot of any of *scope_ids* right now, in which case it
        gets it before a request from the scheduler does."""
        if not self._unscheduled_waiters:
            return False
        return any(
            self._can_use_slot_now(waiter, scope_id)
            for scope_id in scope_ids
            for waiter in self._unscheduled_waiters.get(scope_id, ())
        )

    def _can_use_slot_now(self, request: Request, scope_id: ScopeID) -> bool:
        """Return whether *request* would be sent right away if it got a free
        slot of *scope_id*, i.e. whether every one of its other scopes already
        allows it through. A request that would keep waiting on another scope
        has no claim on the slot, so the scheduler may take it."""
        now = time.monotonic()
        if self._request_delay_deadline(request, now) > now:
            return False
        for other_id, quota_amount in self._cached_scope_quota_amounts(request):
            if other_id == scope_id:
                continue
            manager = self._live_scope_manager(other_id)
            if manager is None:
                continue
            if (
                manager.can_send(now=now, quota_amount=quota_amount) > 0
                or manager.concurrency_blocked()
            ):
                return False
        return True

    # -- Synchronous readiness API (used by a throttler-aware scheduler) ------

    def is_ready(self, request: Request) -> bool:
        now = time.monotonic()
        if self._request_delay_deadline(request, now) > now:
            return False
        if request.meta.get("dont_throttle"):
            return True
        scope_values = self._cached_scope_quota_amounts(request)
        for scope_id, quota_amount in scope_values:
            manager = self._live_scope_manager(scope_id)
            if manager is None:
                continue
            if manager.can_send(now=now, quota_amount=quota_amount) > 0:
                return False
            if manager.concurrency_blocked():
                return False
        # Every scope has a free slot, but an unscheduled request waiting for one
        # of them gets it first. Checked here too, to skip building the scope id
        # list for a waiter set that is empty most of the time.
        if not self._unscheduled_waiters:
            return True
        return not self._unscheduled_claims([scope_id for scope_id, _ in scope_values])

    def reserve(self, request: Request) -> None:
        # Reserving twice would record two sends that only one release() undoes,
        # leaving the scope permanently short of a concurrency slot. It takes an
        # unsupported crawl (the same Request object scheduled twice) to get
        # here, so this only keeps that from corrupting scope state for good.
        if request in self._reserved or request.meta.get("dont_throttle"):
            return
        self._record_reservation(
            request,
            self._resolve_scope_slots(self._cached_scope_quota_amounts(request)),
        )

    def get_time_until_ready(self, request: Request) -> float | None:
        now = time.monotonic()
        wait = max(0.0, self._request_delay_deadline(request, now) - now)
        if not request.meta.get("dont_throttle"):
            for scope_id, quota_amount in self._cached_scope_quota_amounts(request):
                manager = self._live_scope_manager(scope_id)
                if manager is None:
                    continue
                wait = max(wait, manager.can_send(now=now, quota_amount=quota_amount))
        return wait if wait > 0 else None

    def get_scope_load(self, scope_id: ScopeID) -> float:
        # A scope with no manager has nothing in flight, so its load is 0: it was
        # either never used, or evicted, which only happens to idle scopes. A
        # priority queue asks for the load of every queued scope on every pop
        # (see DownloaderAwarePriorityQueue), so this must not create one.
        manager = self._live_scope_manager(scope_id)
        return 0.0 if manager is None else manager.get_load()

    def get_request_delay(self, request: Request, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        return max(0.0, self._request_delay_deadline(request, now) - now)

    async def _wait_for_slot(self, managers: list[Any], *, unscheduled: bool) -> None:
        """Block until any of *managers* frees a concurrency slot or, for an
        unscheduled request, until one of them may have a slot to lend.

        A slot becomes available on
        :meth:`~ThrottlingScopeManagerProtocol.record_done` or
        :meth:`~ThrottlingScopeManagerProtocol.set_concurrency`, both of which
        fire the manager event. An unscheduled request may also borrow the slot
        of a holder that reaches the downloader middlewares (see
        :meth:`_can_lend_slot`), which fires no manager event, hence the
        downloader event.

        Every event is registered before this coroutine gives up control, or one
        firing in between would go unnoticed.
        """
        pairs = [(manager, manager.slot_available_event()) for manager in managers]
        events = [event for _, event in pairs]
        downloader = self._downloader() if unscheduled else None
        middlewares_event: Deferred[None] | None = None
        if downloader is not None:
            middlewares_event = downloader._downloader_middlewares_event()
            events.append(middlewares_event)
        _, pending = await wait_for_first(events)
        for manager, event in pairs:
            if event in pending:
                manager.discard_slot_available_event(event)
        if middlewares_event is not None and middlewares_event in pending:
            assert downloader is not None
            downloader._discard_downloader_middlewares_event(middlewares_event)

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
        _mark_request_delayed(request)

    def _request_delay_deadline(self, request: Request, now: float) -> float:
        """Return the monotonic time before which *request* must not be sent due
        to its :reqmeta:`delay`, or ``0.0`` if it has none.

        This is the readiness-API counterpart of :meth:`_delay_request`: a
        throttler-aware scheduler holds the request back until this deadline
        instead of awaiting :meth:`acquire`. The deadline is computed once, the
        first time the request is throttled, and stored so later polls reuse it.
        A request whose delay was already honored (the ``_throttler_delayed``
        flag) is never delayed again, so a resumed crawl does not re-block on a
        stale deadline."""
        delay = request.meta.get("delay")
        if not delay or request.meta.get(_DELAYED_META_KEY):
            return 0.0
        deadline = request.meta.get(_DELAY_DEADLINE_META_KEY)
        if deadline is None:
            deadline = now + float(delay)
            request.meta[_DELAY_DEADLINE_META_KEY] = deadline
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
        if not delay:
            return
        hostname = urlparse_cached(request).hostname or ""
        # A Crawl-delay belongs to a host, so it is applied to the scope that
        # stands for that host, i.e. the one whose id is the host name, and only
        # if *request* is actually being sent under it. Under custom scoping
        # there may be no such scope, and the delay cannot be attributed to any
        # of the others: a scope shared with other hosts (e.g. one grouping
        # requests by API cost) would slow those hosts down too.
        if hostname not in set(iter_scopes(self.get_resolved_scopes(request))):
            self._warn_unscoped_robots_crawl_delay(hostname)
            return
        self._apply_robots_crawl_delay(hostname, delay)

    def _warn_unscoped_robots_crawl_delay(self, hostname: ScopeID) -> None:
        if self._robotstxt_scope_warned:
            return
        self._robotstxt_scope_warned = True
        logger.warning(
            f"Ignoring the robots.txt Crawl-delay of {hostname!r} because "
            f"requests for that host are not sent under a throttling scope "
            f"named after it, so there is no scope to apply the delay to. "
            f"Include {hostname!r} in the scopes of those requests to honor it, "
            f"or set THROTTLER_ROBOTSTXT_OBEY to False to silence this warning. "
            f"Further occurrences are not reported."
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
        # From the next request of the scope on: the request that triggered the
        # robots.txt download was allowed through before the delay was known, and
        # its send is already recorded.
        self.get_scope_manager(scope_id).set_base_delay(capped)


class ThrottlingScopeManagerProtocol(Protocol):
    """A protocol for :setting:`THROTTLING_SCOPE_MANAGER` :ref:`components
    <topics-components>`.

    An instance manages one throttling scope's run-time throttling state: its
    delay and concurrency limits, its quota, and any gradual :ref:`backoff
    <backoff>`.

    An instance is created the first time its scope is actually used (a request
    is sent under it, it backs off, its delay is read or written), not when a
    scope is merely considered: until then the scope is taken to impose no wait
    and no concurrency limit, so the very first request of a scope is never held
    back by it. An instance may also be dropped once its scope is idle (see
    :setting:`THROTTLING_SCOPE_LIMIT`) and recreated from its configuration
    later, so it must not be relied upon to accumulate state across idle
    periods.

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
        <throttler-quotas>` consumption of the request, if any.
        """

    def record_sent(
        self, now: float | None = None, quota_amount: QuotaAmount | None = None
    ) -> None:
        """Record that a request for this scope has just been sent, consuming
        *quota_amount* of its :ref:`throttler quota <throttler-quotas>` if
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
        """Reconcile the :ref:`throttler quota <throttler-quotas>` of this
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

    def get_concurrency(self) -> int:
        """Return the maximum number of concurrent requests allowed for this
        scope.

        :class:`Throttler` compares this against the number of the scope's
        requests that are in a download handler, to keep a request that holds a
        concurrency slot without using it from letting more of them there at
        once than this allows; see
        :meth:`ThrottlerProtocol.download_handler_blocked`."""

    def set_concurrency(self, concurrency: int) -> None:
        """Set the maximum number of concurrent requests allowed for this
        scope, which must be ``1`` or higher.

        There is no way to lift the limit: a scope always enforces one. The
        reference implementation raises :exc:`ValueError` on a lower value."""

    def concurrency_blocked(self) -> bool:
        """Return whether this scope is at its concurrency limit.

        :class:`Throttler` calls this (once every time-based limit in
        :meth:`can_send` has elapsed) to decide whether to wait for a freed slot.
        Return ``False`` when no concurrency limit is enforced.
        """

    def get_load(self) -> float:
        """Return the current load of this scope: a non-negative number, with
        ``1.0`` meaning "as busy as its concurrency limit allows".

        A :ref:`throttler-aware scheduler <throttler-aware-scheduler>` uses
        this to break ties between equally-prioritized requests, preferring the
        least-loaded scopes. The reference implementation returns active sends
        divided by the concurrency limit, but any consistent busyness metric
        works; return ``0.0`` when none is meaningful.
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

    def is_idle(self, now: float) -> bool:
        """Return whether this scope can be evicted from memory, i.e. whether it
        holds no state that eviction would drop: no active (future) backoff, no
        pending delay and no spent quota in the current window.

        It must also return ``False`` while any :meth:`record_sent` request of
        the scope is still in flight, i.e. has not been passed to
        :meth:`record_done` yet. Eviction replaces the instance, and the
        replacement starts with no request in flight, so a scope evicted while
        holding one lets through as many concurrent requests as its limit allows
        *on top of* those already out.
        """


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
    <throttler-quotas>`:

    -   A base delay (the scope ``"delay"`` config, defaulting to
        :setting:`DOWNLOAD_DELAY`) is enforced between consecutive requests for
        the scope.

    -   On a backoff trigger the delay grows (see :meth:`record_backoff`); after
        quiet recovery windows it recovers (see :meth:`_recover`). The
        :ref:`backoff docs <backoff>` describe the algorithm. Backoff can be
        turned off for a scope with the ``"backoff"`` config's ``"enabled"``
        key, leaving it to rely solely on its delay and quota.

    -   No more than ``"concurrency"`` requests (defaulting to
        :setting:`THROTTLING_SCOPE_CONCURRENCY`) are allowed in flight at once.
        There is no way to lift this limit.

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
        # defaulting to RANDOMIZE_DOWNLOAD_DELAY's historical ±50% when delay
        # randomization is on, and to no variation when it is off.
        self._jitter: float = float(
            config.get(
                "jitter", 0.5 if settings.getbool("RANDOMIZE_DOWNLOAD_DELAY") else 0.0
            )
        )
        self._delay_factor: float = _BACKOFF_DELAY_FACTOR
        self._max_delay: float = float(
            backoff.get("max_delay", settings.getfloat("BACKOFF_MAX_DELAY"))
        )
        self._min_delay: float = _BACKOFF_MIN_DELAY
        self._backoff_jitter: float = _BACKOFF_JITTER
        # Which responses/exceptions trigger backoff is decided by the backoff
        # middleware (see BackoffMiddleware), which reads the same per-scope
        # "http_codes"/"exceptions" config and the global BACKOFF_* settings.
        self._window: float = _BACKOFF_WINDOW

        # Concurrency. Always limited: a scope has no way to express "no limit"
        # (see _check_scope_concurrency), so this is a positive integer.
        self._concurrency: int = int(
            config.get("concurrency", _default_scope_concurrency(settings))
        )

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
        self._slot_available = _Event()
        self._consumed: float = 0.0
        self._quota_window_start: float | None = None

    @staticmethod
    def _now(now: float | None) -> float:
        return time.monotonic() if now is None else now

    @staticmethod
    def _apply_jitter(value: float, jitter: float) -> float:
        """Spread *value* by ±*jitter*, e.g. a *jitter* of ``0.5`` returns
        ``value * uniform(0.5, 1.5)``."""
        if not jitter:
            return value
        return value * (1 + random.uniform(-jitter, jitter))  # noqa: S311

    def _effective_delay(self) -> float:
        # self._delay is the deterministic delay (the base delay, or the bounded
        # exponential value while backing off). Jitter is applied per use, so
        # that it neither compounds across steps nor piles probability mass on
        # the min/max bounds, which clipping a jittered value would do.
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
            self._slot_available.fire()

    def concurrency_blocked(self) -> bool:
        return self._active >= self._concurrency

    def get_load(self) -> float:
        return self._active / self._concurrency

    def slot_available_event(self) -> Deferred[None]:
        return self._slot_available.wait()

    def discard_slot_available_event(self, event: Deferred[None]) -> None:
        self._slot_available.discard(event)

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
            # A hard delay (e.g. Retry-After) is a one-time hold, not the
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
        # Checked before the base changes.
        backing_off = self._delay > self._base_delay
        self._base_delay = delay
        # Reflect the change in the effective delay, unless a backoff is raising
        # it above the new base right now. A backoff that no longer clears the
        # base is over, and leaving the delay below the base would apply neither
        # value, since _recover() also gives up once within the base.
        if not backing_off or self._delay < delay:
            self._delay = delay

    def get_concurrency(self) -> int:
        return self._concurrency

    def set_concurrency(self, concurrency: int) -> None:
        concurrency = int(concurrency)
        if concurrency < 1:
            raise ValueError(
                f"Scope concurrency must be 1 or higher, got {concurrency!r}."
            )
        self._concurrency = concurrency
        self._slot_available.fire()

    def is_idle(self, now: float) -> bool:
        if self._in_backoff_until is not None and self._in_backoff_until > now:
            return False
        # A delay that has not elapsed yet would let the next request for the
        # scope go out earlier than its delay allows.
        if self._next_allowed_time is not None and self._next_allowed_time > now:
            return False
        # A quota window with something spent in it would give the scope a full
        # quota again before its window is over.
        window_start = self._quota_window_start
        if (
            self._consumed > 0
            and window_start is not None
            and now - window_start < self._quota_window
        ):
            return False
        return self._active == 0
