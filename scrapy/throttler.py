from __future__ import annotations

import json
import logging
import math
import random
import sys
import time
import warnings
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, Protocol, Self, TypedDict, cast
from weakref import WeakKeyDictionary, WeakSet

from twisted.internet.defer import Deferred

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import SETTINGS_PRIORITIES
from scrapy.utils.asyncio import call_later
from scrapy.utils.defer import _Event
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from scrapy.core.downloader import Downloader
    from scrapy.crawler import Crawler
    from scrapy.http import Request
    from scrapy.settings import BaseSettings
    from scrapy.utils.asyncio import CallLaterResult


logger = logging.getLogger(__name__)


class ThrottlingScopeConfig(TypedDict, total=False):
    """Accepted keys of :setting:`THROTTLING_SCOPES` entries."""

    concurrency: int
    """Per-scope override of :setting:`THROTTLING_SCOPE_CONCURRENCY`."""

    delay: float
    """Per-scope override of :setting:`DOWNLOAD_DELAY`."""

    jitter: float
    """Per-scope override of :setting:`DOWNLOAD_DELAY_JITTER`."""


ScopeID = str
RequestScopes = None | ScopeID | Iterable[ScopeID]
if TYPE_CHECKING:
    # A scope of a request being throttled: its ID and its manager.
    ScopeSlot = tuple[ScopeID, "ThrottlingScopeManager"]


def _normalize_scopes(scopes: RequestScopes) -> list[ScopeID]:
    """Return the scope IDs of *scopes*, whatever the form
    :meth:`~ThrottlerProtocol.get_scopes` returned them in, as a list.

    A one-shot iterable is materialized here, so that the result stays
    re-iterable and serializable.
    """
    if scopes is None:
        return []
    if isinstance(scopes, str):
        return [scopes]
    return list(scopes)


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
    if (
        domain_priority > scope_priority
        or scope_priority == domain_priority <= SETTINGS_PRIORITIES["default"]
    ):
        return "CONCURRENT_REQUESTS_PER_DOMAIN"
    return "THROTTLING_SCOPE_CONCURRENCY"


def _default_scope_concurrency(settings: BaseSettings) -> int:
    """Return the default concurrency of a throttling scope that does not set
    its own ``concurrency``, i.e. the value of the setting chosen by
    :func:`_default_scope_concurrency_setting`."""
    return settings.getint(_default_scope_concurrency_setting(settings))


def _default_jitter(settings: BaseSettings) -> float:
    """Return the default magnitude of the random variation applied to the delay
    of a throttling scope that does not set its own ``jitter``:
    :setting:`DOWNLOAD_DELAY_JITTER`, or the deprecated
    ``RANDOMIZE_DOWNLOAD_DELAY`` when set at a higher :ref:`priority
    <populating-settings>`, mapped to ±50% or none (see
    :func:`_warn_on_deprecated_randomization`)."""
    if _effective_priority(settings, "RANDOMIZE_DOWNLOAD_DELAY") > _effective_priority(
        settings, "DOWNLOAD_DELAY_JITTER"
    ):
        return 0.5 if settings.getbool("RANDOMIZE_DOWNLOAD_DELAY") else 0.0
    return settings.getfloat("DOWNLOAD_DELAY_JITTER")


def _warn_on_ignored_per_ip(settings: BaseSettings) -> None:
    """Warn that :setting:`CONCURRENT_REQUESTS_PER_IP` no longer has any effect.
    Call once per crawl (see :meth:`Throttler.__init__`).

    Nothing reads the setting anymore, so without this a crawl that sets it
    would silently stop limiting concurrency per IP.
    """
    if (
        _effective_priority(settings, "CONCURRENT_REQUESTS_PER_IP")
        <= SETTINGS_PRIORITIES["default"]
    ):
        return
    warnings.warn(
        "The CONCURRENT_REQUESTS_PER_IP setting is deprecated and no longer "
        "has any effect. To limit concurrency per IP address, define a "
        "throttling scope for it: "
        "https://docs.scrapy.org/en/latest/topics/throttling.html#throttling-per-ip",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )


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


def _warn_on_deprecated_randomization(settings: BaseSettings) -> None:
    """Warn that :setting:`RANDOMIZE_DOWNLOAD_DELAY` is deprecated when it is
    set. Call once per crawl (see :meth:`Throttler.__init__`).

    Both defaults mean the same ±50%, so a crawl that sets neither needs no
    warning.
    """
    if (
        _effective_priority(settings, "RANDOMIZE_DOWNLOAD_DELAY")
        <= SETTINGS_PRIORITIES["default"]
    ):
        return
    warnings.warn(
        "The RANDOMIZE_DOWNLOAD_DELAY setting is deprecated, use "
        "DOWNLOAD_DELAY_JITTER instead: it takes the magnitude of the random "
        "variation as a number, e.g. 0.5 for the ±50% that "
        "RANDOMIZE_DOWNLOAD_DELAY enables, or 0 to disable it.",
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
    """Reject negative throttling scope concurrency limits. Call once per crawl
    (see :meth:`Throttler.__init__`)."""
    name = _default_scope_concurrency_setting(settings)
    concurrency = settings.getint(name)
    if concurrency < 0:
        raise ValueError(f"{name} must be 0 or higher, got {concurrency!r}.")
    for scope_id, config in scopes_config.items():
        if config.get("concurrency") is None:
            continue
        concurrency = int(config["concurrency"])
        if concurrency < 0:
            raise ValueError(
                f"The concurrency of throttling scope {scope_id!r} must be 0 or "
                f"higher, got {concurrency!r}."
            )


class ThrottlerProtocol(Protocol):
    """A protocol for :setting:`THROTTLER` :ref:`components
    <topics-components>`."""

    def get_scopes(self, request: Request) -> RequestScopes:
        """Return the :ref:`throttling scopes <throttling-scopes>` that apply
        to *request*.

        Return ``None`` if no scopes apply, a string for a single scope, or an
        iterable of strings for multiple scopes.

        This is the extension point for custom scoping; see
        :ref:`custom-throttler`.
        """

    def get_applied_scopes(self, request: Request) -> list[ScopeID]:
        """Return the :ref:`throttling scopes <throttling-scopes>` under which
        *request* was (or will be) sent.

        Use it, rather than :meth:`get_scopes`, to attribute a response or
        exception to the very scopes the request was sent under — e.g. from a
        downloader middleware or a spider callback that wants to adjust the delay
        of those scopes based on the response.
        """

    def acquire(
        self,
        request: Request,
        *,
        retry: Callable[[], None],
        unscheduled: bool = False,
    ) -> float | None:
        """Reserve a concurrency slot of every scope of *request* and return
        ``None`` if they all allow *request* to be sent right now.

        Otherwise, return the number of seconds after which the engine is to
        call this method again for *request*, or :data:`math.inf` for the engine
        to wait until *retry* is called. Call *retry* whenever something that
        holds *request* back may have changed, e.g. when a concurrency slot of
        one of its scopes frees up; a premature call only costs another attempt.

        The engine calls this before handing a request to the downloader, again
        and again until it returns ``None`` or the engine drops the request.

        *unscheduled* tells whether *request* was sent without going through the
        scheduler, i.e. through :meth:`crawler.engine.download_async()
        <scrapy.core.engine.ExecutionEngine.download_async>`. Such a request may
        be a prerequisite of a request that holds a concurrency slot of the same
        scope while it waits for it, as the built-in robots.txt middleware does,
        so an implementation must make sure it can never be blocked by such a
        request forever.

        A request with the :reqmeta:`dont_throttle` metadata key is not held by
        its scopes and does not count towards them; only its own
        :reqmeta:`delay`, if any, still applies.
        """

    def release(self, request: Request) -> None:
        """Release the concurrency slots that :meth:`acquire` reserved for
        *request*.

        The engine calls this once *request* has finished downloading (whether
        it succeeded, failed or returned a new request), so that scopes that
        enforce a concurrency limit can let other requests through, and also
        when it drops a request that :meth:`acquire` did not let through.
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

    def get_scopes_key(self, request: Request) -> str:
        """Return a single string key for *request*, derived from its scopes.

        For a single scope this is the scope ID itself; for multiple scopes the
        sorted scope IDs are JSON-encoded into an order-independent,
        collision-free key. The scheduler uses it to group queued requests by
        scope.

        Resolve the scopes anew on every call, so that a request that inherited
        ``request.meta`` from another one (e.g. a redirect) gets its own scopes
        rather than the inherited ones.
        """

    def get_scope_load(self, scope_id: str) -> float:
        """Return the current load of the scope identified by *scope_id*: its
        active sends divided by its concurrency limit, which
        :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue` uses to prefer the
        least-loaded scopes when dequeuing.

        It can exceed ``1.0``: lending an unused slot (see the *unscheduled*
        argument of :meth:`acquire`) makes the outstanding sends of a scope
        outnumber its concurrency until the borrowers drain.

        A scope with no throttling state yet has a load of ``0.0``.
        Implementations should not create state just to answer this: it is
        called for every queued scope on every dequeue.
        """

    def get_scope_manager(self, scope_id: str) -> ThrottlingScopeManager:
        """Return the :class:`ThrottlingScopeManager` instance handling the scope
        identified by *scope_id*, creating it if necessary.

        Use it to read or drive the state of a scope directly, e.g. to set its
        delay with :meth:`~ThrottlingScopeManager.set_base_delay`."""


# Request.meta key under which Throttler._resolve_scopes() persists the scopes of
# a request so that they survive it being serialized to and restored from a disk
# queue.
_APPLIED_SCOPES_META_KEY = "_throttler_applied_scopes"

# Request.meta key under which the downloader records the 'download_slot' value
# it set itself (see Downloader._enqueue_request), so that the deprecation of
# that meta key is only reported for values that a user set; see
# Throttler._resolve_scopes_sync.
_STAMPED_SLOT_META_KEY = "_throttler_stamped_download_slot"

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
    request.meta[_DELAY_DEADLINE_META_KEY] = (delay, time.time() + delay)
    request.meta["delayed"] = [*request.meta.get("delayed", []), delay]


class Throttler(ThrottlerProtocol):
    """The default :setting:`THROTTLER` class.

    It assigns to each request its domain or subdomain as scope.

    Subclass it and override :meth:`get_scopes` to assign scopes differently.
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
        _warn_on_deprecated_randomization(crawler.settings)
        _warn_on_ignored_per_ip(crawler.settings)
        _warn_on_unachievable_concurrency(crawler.settings, self._scopes_config)
        self._debug = crawler.settings.getbool("THROTTLER_DEBUG")
        self._scope_defaults: dict[str, Any] = {
            "concurrency": _default_scope_concurrency(crawler.settings),
            "delay": crawler.settings.getfloat("DOWNLOAD_DELAY"),
            "jitter": _default_jitter(crawler.settings),
        }
        # Ordered by least-recently-used first (see get_scope_manager), so the
        # scope limit can evict the coldest idle scopes (see THROTTLING_SCOPE_LIMIT).
        self._scope_managers: OrderedDict[ScopeID, ThrottlingScopeManager] = (
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
        # Unscheduled requests that acquire() has not let through yet, by
        # scope, so that a slot freed in one of those scopes goes to them before
        # it goes to a request from the scheduler (see _unscheduled_claims).
        self._unscheduled_waiters: dict[ScopeID, WeakSet[Request]] = {}
        # Requests from the scheduler that acquire() held back once in favor of
        # an unscheduled request, which it does not do twice.
        self._yielded: set[Request] = set()
        # The slot events that acquire() registered each retry of each request
        # on, each with the callable that discards it. Retries are told apart
        # because the same request can wait more than once at a time, e.g. as
        # the prerequisite of two requests.
        self._waits: dict[
            Request,
            dict[
                Callable[[], None],
                list[tuple[Deferred[None], Callable[[Deferred[None]], None]]],
            ],
        ] = {}

    @staticmethod
    def _merge_download_slots(settings: BaseSettings) -> dict[str, dict[str, Any]]:
        """Return the effective per-scope configuration, merging the deprecated
        :setting:`DOWNLOAD_SLOTS` setting into :setting:`THROTTLING_SCOPES`.

        Each ``DOWNLOAD_SLOTS`` entry is translated to a throttling scope keyed
        by the same slot name (the default manager keys domain scopes by host
        name, matching how download slots are keyed): ``concurrency``,
        ``delay`` and ``jitter`` map directly, and the deprecated
        ``randomize_delay`` boolean maps to a ``jitter`` magnitude (±50%, or
        none). An explicit
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
            if "jitter" in slot_config:
                translated["jitter"] = slot_config["jitter"]
            elif "randomize_delay" in slot_config:
                translated["jitter"] = 0.5 if slot_config["randomize_delay"] else 0.0
            scopes[slot_id] = {**translated, **scopes.get(slot_id, {})}
        return scopes

    def get_scopes(self, request: Request) -> RequestScopes:
        """Return the :ref:`throttling scopes <throttling-scopes>` of *request*:
        its :reqmeta:`throttling_scopes` metadata key if set, and otherwise its
        host name.
        """
        meta = request.meta
        scopes: RequestScopes = meta.get("throttling_scopes")
        if scopes is not None:
            return scopes
        download_slot: RequestScopes = meta.get("download_slot")
        # A value the downloader stamped (see Downloader._enqueue_request) is
        # bookkeeping rather than intent: honoring the one a derived request (a
        # redirect, a retry) inherits would keep it in the scope of a different
        # host. Anything else is a user's choice of scope.
        if download_slot is not None and download_slot != meta.get(
            _STAMPED_SLOT_META_KEY
        ):
            warnings.warn(
                "The 'download_slot' request meta key is deprecated. Use "
                "'throttling_scopes' instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
            return download_slot
        return urlparse_cached(request).hostname or ""

    def _resolve_scopes(self, request: Request) -> list[ScopeID]:
        """Return the :ref:`throttling scopes <throttling-scopes>` of *request*
        and persist them on ``request.meta``, where :meth:`get_applied_scopes`
        reads them back, and whence they survive the request being serialized to
        and restored from a :ref:`disk queue <topics-jobs>`.

        Every call resolves anew, so a request that inherited ``request.meta``
        from another one (e.g. a redirect built with :meth:`Request.replace()
        <scrapy.Request.replace>`, which copies ``meta``) replaces the inherited
        scopes with its own.
        """
        scope_ids = _normalize_scopes(self.get_scopes(request))
        request.meta[_APPLIED_SCOPES_META_KEY] = scope_ids
        return scope_ids

    def get_scopes_key(self, request: Request) -> str:
        scope_ids = self._resolve_scopes(request)
        if not scope_ids:
            return ""
        if len(scope_ids) == 1:
            return scope_ids[0]
        return json.dumps(sorted(scope_ids))

    def get_applied_scopes(self, request: Request) -> list[ScopeID]:
        if _APPLIED_SCOPES_META_KEY in request.meta:
            return cast("list[ScopeID]", request.meta[_APPLIED_SCOPES_META_KEY])
        return self._resolve_scopes(request)

    # -- Scope-state coordination (called from the request lifecycle) --------

    def get_scope_manager(self, scope_id: ScopeID) -> ThrottlingScopeManager:
        manager = self._scope_managers.get(scope_id)
        if manager is not None:
            # Mark as most-recently-used for the LRU scope limit.
            self._scope_managers.move_to_end(scope_id)
            return manager
        config: dict[str, Any] = {
            **self._scope_defaults,
            "id": scope_id,
            **self._scopes_config.get(scope_id, {}),
        }
        manager = build_from_crawler(ThrottlingScopeManager, self.crawler, config)
        self._scope_managers[scope_id] = manager
        self._enforce_scope_limit(scope_id)
        return manager

    def _resolve_scope_slots(self, scope_ids: list[ScopeID]) -> list[ScopeSlot]:
        """Return the ``ScopeSlot`` of every scope in *scope_ids*.

        Resolved together, and marked as such in :attr:`_resolving`, because
        :meth:`get_scope_manager` enforces :setting:`THROTTLING_SCOPE_LIMIT` as
        soon as it creates a manager and only spares the scope it created:
        one at a time, a scope of this request could evict another one.
        """
        if len(scope_ids) == 1:
            return [(scope_ids[0], self.get_scope_manager(scope_ids[0]))]
        self._resolving.update(scope_ids)
        try:
            return [
                (scope_id, self.get_scope_manager(scope_id)) for scope_id in scope_ids
            ]
        finally:
            self._resolving.clear()

    def _live_scope_manager(self, scope_id: ScopeID) -> ThrottlingScopeManager | None:
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
        :meth:`~ThrottlingScopeManager._is_idle` scopes are evicted, and
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
                and manager._is_idle(now)
            ):
                evictable.append(scope_id)
        for scope_id in evictable:
            del self._scope_managers[scope_id]

    def acquire(
        self,
        request: Request,
        *,
        retry: Callable[[], None],
        unscheduled: bool = False,
    ) -> float | None:
        if self._stop_waiting(request, retry):
            # A retry after waiting for a slot, which only happens once the delay
            # has elapsed and the scopes are resolved.
            scope_ids = cast("list[ScopeID]", request.meta[_APPLIED_SCOPES_META_KEY])
        else:
            wait = self._delay(request)
            if wait > 0:
                return wait
            # The scopes are resolved (and persisted, see _resolve_scopes) even
            # for a request excluded from throttling, because its outcome still
            # backs off its scopes, and get_applied_scopes() is how a middleware
            # finds them.
            scope_ids = self._resolve_scopes(request)
            if request.meta.get("dont_throttle") or not scope_ids:
                return None
            if unscheduled:
                # A registration here makes the whole scope yield its free slots
                # to this request (see _unscheduled_claims), so it is undone once
                # the request is let through or released.
                for scope_id in scope_ids:
                    self._unscheduled_waiters.setdefault(scope_id, WeakSet()).add(
                        request
                    )
        slot_wait = self._acquire_scope_slots(
            request, scope_ids, retry=retry, unscheduled=unscheduled
        )
        if slot_wait is None and unscheduled:
            self._forget_unscheduled(request, scope_ids)
        return slot_wait

    def _acquire_scope_slots(
        self,
        request: Request,
        scope_ids: list[ScopeID],
        *,
        retry: Callable[[], None],
        unscheduled: bool,
    ) -> float | None:
        """Reserve a slot on every scope in *scope_ids* if they all allow
        *request* through, and otherwise return how long until another attempt
        is worth it, see :meth:`acquire`.

        The scope managers are resolved anew on every attempt: a scope can be
        evicted between attempts (see :setting:`THROTTLING_SCOPE_LIMIT`), and
        recording the send on a replaced manager would leave the scope with two
        sets of counters, letting it exceed its limits.
        """
        # A second send that only one release() undoes would leave these scopes
        # permanently short of a slot. It takes an unsupported crawl (one
        # Request object downloaded twice at once) to get here.
        if request in self._reserved:
            return None
        scopes = self._resolve_scope_slots(scope_ids)
        wait = (
            scopes[0][1]._can_send()
            if len(scopes) == 1
            else max(manager._can_send() for _, manager in scopes)
        )
        if wait > 0:
            if self._debug:
                logger.debug(
                    f"Throttling {request} for {wait:.2f}s (scopes: {scope_ids})"
                )
            return wait
        # The delay has elapsed; the only remaining reason to wait is a full
        # concurrency slot.
        blocked: list[ScopeSlot] = []
        free: list[ScopeSlot] = []
        for scope_id, manager in scopes:
            if manager._concurrency_blocked():
                blocked.append((scope_id, manager))
            else:
                free.append((scope_id, manager))
        if not blocked:
            if (
                not unscheduled
                and self._unscheduled_claims(scope_ids)
                and request not in self._yielded
            ):
                # An unscheduled request waiting for one of these scopes can use
                # the free slot right now, and something in flight may be
                # waiting for it, so let it go first. Only once, so that a claim
                # that no one takes cannot hold this request back for good.
                self._yielded.add(request)
                return 0.0
            if self._yielded:
                self._yielded.discard(request)
            self._record_reservation(request, scopes)
            return None
        if unscheduled and all(
            self._can_lend_slot(scope_id) for scope_id, _ in blocked
        ):
            self._borrow_slots(request, scopes, [scope_id for scope_id, _ in blocked])
            return None
        if self._debug:
            logger.debug(
                f"Throttling {request} until a concurrency slot frees up "
                f"(scopes: {scope_ids})"
            )
        self._wait_for_slot(
            request,
            [manager for _, manager in blocked],
            retry=retry,
            unscheduled=unscheduled,
        )
        # A scope with room while another one holds this request back may have
        # woken it for a slot it is not going to take, and only one waiter is
        # woken per freed slot, so that slot would sit unused.
        for _, manager in free:
            manager._wake_waiters()
        return math.inf

    def _wait_for_slot(
        self,
        request: Request,
        managers: list[ThrottlingScopeManager],
        *,
        retry: Callable[[], None],
        unscheduled: bool,
    ) -> None:
        """Have *retry* called once any of *managers* frees a concurrency slot
        or, for an unscheduled *request*, once one of them may have a slot to
        lend.

        A slot becomes available on
        :meth:`~ThrottlingScopeManager._record_done` or
        :meth:`~ThrottlingScopeManager.set_concurrency`, both of which fire the
        manager event. An unscheduled request may also borrow the slot of a
        holder that reaches the downloader middlewares (see
        :meth:`_can_lend_slot`), which fires no manager event, hence the
        downloader event.
        """
        waits = self._waits.setdefault(request, {}).setdefault(retry, [])
        for manager in managers:
            waits.append(
                (manager._slot_available_event(), manager._discard_slot_available_event)
            )
        downloader = self._downloader() if unscheduled else None
        if downloader is not None:
            waits.append(
                (
                    downloader._downloader_middlewares_event(),
                    downloader._discard_downloader_middlewares_event,
                )
            )
        for event, _ in waits:
            event.addCallback(lambda _: retry())

    def _stop_waiting(
        self, request: Request, retry: Callable[[], None] | None = None
    ) -> bool:
        """Discard the slot events registered by :meth:`_wait_for_slot` for
        *retry* of *request*, or for every retry of it, which the next attempt
        registers again if it still has to wait, and return whether there were
        any."""
        if not self._waits:
            return False
        by_retry = self._waits.get(request)
        if not by_retry:
            return False
        if retry is None:
            waits = [wait for retry_waits in by_retry.values() for wait in retry_waits]
            by_retry.clear()
        else:
            waits = by_retry.pop(retry, [])
        if not by_retry:
            del self._waits[request]
        for event, discard in waits:
            # A fired event is no longer registered.
            if not event.called:
                discard(event)
        return bool(waits)

    def _forget_unscheduled(self, request: Request, scope_ids: list[ScopeID]) -> None:
        for scope_id in scope_ids:
            waiters = self._unscheduled_waiters.get(scope_id)
            if waiters is not None:
                waiters.discard(request)
                if not waiters:
                    del self._unscheduled_waiters[scope_id]

    def _record_reservation(self, request: Request, scopes: list[ScopeSlot]) -> None:
        """Record a send on each of *request*'s *scopes* and mark *request* as
        reserved, so :meth:`release` can later free the slots."""
        for scope_id, manager in scopes:
            manager._record_sent()
            self._scope_holders.setdefault(scope_id, WeakSet()).add(request)
        self._reserved[request] = scopes

    def release(self, request: Request) -> None:
        self._stop_waiting(request)
        if self._yielded:
            self._yielded.discard(request)
        if self._unscheduled_waiters:
            self._forget_unscheduled(
                request, request.meta.get(_APPLIED_SCOPES_META_KEY, [])
            )
        scopes = self._reserved.pop(request, None)
        if not scopes:
            return
        for scope_id, manager in scopes:
            holders = self._scope_holders.get(scope_id)
            if holders is not None:
                holders.discard(request)
                if not holders:
                    del self._scope_holders[scope_id]
            manager._record_done()

    # -- Unscheduled requests ---------------------------------------------------

    def _downloader(self) -> Downloader | None:
        engine = self.crawler._engine
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
        for scope_id, manager in scopes:
            # *request* itself holds a slot of every scope it reserved, so the
            # scope has holders.
            holders = self._scope_holders[scope_id]
            concurrency = manager.get_concurrency()
            # *request* is one of the holders and has not reached a handler yet,
            # so up to that many holders leave too few of them for the count
            # below to reach the limit. Only a lent slot (see _can_lend_slot)
            # takes a scope past that, so this skips the scan almost always.
            if len(holders) <= concurrency:
                continue
            # *request* has not reached a handler yet, so it does not count
            # itself.
            in_handlers = sum(1 for holder in holders if holder in in_download_handler)
            if in_handlers >= concurrency:
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
        self.crawler.stats.inc_value("throttler/borrowed_slots")
        if self._debug:
            logger.debug(
                f"Letting {request} borrow a concurrency slot of every scope in "
                f"{borrowed}, whose slots are all held by requests that no "
                f"download handler is working on"
            )
        self._record_reservation(request, scopes)

    def _unscheduled_claims(self, scope_ids: list[ScopeID]) -> bool:
        """Return whether an unscheduled request that :meth:`acquire` holds back
        could use a free slot of any of *scope_ids* right now, in which case it
        gets it before a request from the scheduler does."""
        if not self._unscheduled_waiters:
            return False
        # A waiter only claims the slot if every one of its other scopes already
        # allows it through; one that would keep waiting on another scope has no
        # claim on it, so the scheduler may take it.
        return any(
            self._scopes_allow(waiter, skip=scope_id)
            for scope_id in scope_ids
            for waiter in self._unscheduled_waiters.get(scope_id, ())
        )

    def _scopes_allow(self, request: Request, *, skip: ScopeID | None = None) -> bool:
        """Return whether every scope of *request*, except *skip*, allows it
        through right now."""
        now = time.monotonic()
        for scope_id in self.get_applied_scopes(request):
            if scope_id == skip:
                continue
            manager = self._live_scope_manager(scope_id)
            if manager is None:
                continue
            if manager._can_send(now=now) > 0 or manager._concurrency_blocked():
                return False
        return True

    def get_scope_load(self, scope_id: ScopeID) -> float:
        # A scope with no manager has nothing in flight, so its load is 0: it was
        # either never used, or evicted, which only happens to idle scopes. A
        # priority queue asks for the load of every queued scope on every pop
        # (see DownloaderAwarePriorityQueue), so this must not create one.
        manager = self._live_scope_manager(scope_id)
        return 0.0 if manager is None else manager._get_load()

    def _delay(self, request: Request) -> float:
        """Return how long to hold *request* for the deadline of its
        :reqmeta:`delay`.

        The wait happens before the request gets a concurrency slot, so it does
        not take one.
        """
        # A request that skipped the scheduler, e.g. one from
        # ExecutionEngine.download_async(), starts its countdown here.
        _start_delay_countdown(request)
        countdown = request.meta.get(_DELAY_DEADLINE_META_KEY)
        if countdown is None:
            return 0.0
        delay, deadline = cast("tuple[float, float]", countdown)
        now = time.time()
        # A deadline further away than the delay means the clock moved backwards
        # since it was set, which takes a crawl resumed from a disk queue, e.g.
        # on a machine with a lagging clock. Capping keeps the wait to what the
        # delay asked for.
        if deadline - now > delay:
            deadline = now + delay
            request.meta[_DELAY_DEADLINE_META_KEY] = (delay, deadline)
        wait = deadline - now
        if wait <= 0:
            del request.meta[_DELAY_DEADLINE_META_KEY]
            return 0.0
        if self._debug:
            logger.debug(f"Holding {request} for {wait:.2f}s (delay)")
        return wait


def _wait_for_throttler(
    throttler: ThrottlerProtocol, request: Request, *, unscheduled: bool = False
) -> Deferred[None]:
    """Return a :class:`~twisted.internet.defer.Deferred` that fires once
    :meth:`~ThrottlerProtocol.acquire` lets *request* through.

    Cancelling it stops trying, and releases *request*.
    """
    timer: CallLaterResult | None = None

    def stop(_: Deferred[None]) -> None:
        if timer is not None:
            timer.cancel()
        throttler.release(request)

    acquired: Deferred[None] = Deferred(stop)

    def attempt() -> None:
        nonlocal timer
        # A retry can come late, e.g. from a timer or an event that another
        # attempt made obsolete.
        if acquired.called:
            return
        if timer is not None:
            timer.cancel()
            timer = None
        try:
            wait = throttler.acquire(request, retry=attempt, unscheduled=unscheduled)
        except Exception:
            acquired.errback()
            return
        if wait is None:
            acquired.callback(None)
        elif wait != math.inf:
            timer = call_later(wait, attempt)

    attempt()
    return acquired


class ThrottlingScopeManager:
    r"""Manager of the run-time throttling state of a single :ref:`throttling
    scope <throttling-scopes>`.

    Instances are created by the throttler; do not instantiate this class
    directly, get the manager of a scope through
    :meth:`~ThrottlerProtocol.get_scope_manager`.

    It implements a per-scope state machine covering delay and concurrency:

    -   A base delay (the scope ``"delay"`` config, defaulting to
        :setting:`DOWNLOAD_DELAY`) is enforced between consecutive requests for
        the scope.

    -   No more than ``"concurrency"`` requests (defaulting to
        :setting:`THROTTLING_SCOPE_CONCURRENCY`) are allowed in flight at once.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler, config: dict[str, Any]) -> Self:
        return cls(crawler, config)

    def __init__(self, crawler: Crawler, config: dict[str, Any]) -> None:
        settings = crawler.settings
        self._id: ScopeID = config.get("id", "")
        self._base_delay: float = float(
            config["delay"]
            if "delay" in config
            else settings.getfloat("DOWNLOAD_DELAY")
        )
        # Magnitude of the random variation applied to the delay, defaulting to
        # DOWNLOAD_DELAY_JITTER.
        self._jitter: float = float(
            config["jitter"] if "jitter" in config else _default_jitter(settings)
        )

        # Concurrency. 0 means no per-scope limit, so CONCURRENT_REQUESTS
        # applies, with sys.maxsize standing in for no limit at all.
        self._no_limit: int = settings.getint("CONCURRENT_REQUESTS") or sys.maxsize
        self._concurrency: int = (
            int(
                config["concurrency"]
                if "concurrency" in config
                else _default_scope_concurrency(settings)
            )
            or self._no_limit
        )

        # State.
        self._next_allowed_time: float | None = None
        self._last_seen: float | None = None
        self._active: int = 0
        self._slot_available = _Event()

    @staticmethod
    def _now(now: float | None) -> float:
        return time.monotonic() if now is None else now

    @staticmethod
    def _apply_jitter(value: float, jitter: float) -> float:
        """Spread *value* by ±*jitter*, e.g. a *jitter* of ``0.5`` returns
        ``value * uniform(0.5, 1.5)``. A *jitter* above ``1`` would reach into
        negative delays, which are floored at ``0``."""
        if not jitter:
            return value
        return max(0.0, value * (1 + random.uniform(-jitter, jitter)))  # noqa: S311

    def _effective_delay(self) -> float:
        # Jitter is applied per use, rather than stored, so that every interval
        # gets its own random variation.
        if self._base_delay <= 0:
            return self._base_delay
        return self._apply_jitter(self._base_delay, self._jitter)

    def _can_send(self, now: float | None = None) -> float:
        # Concurrency is enforced separately, via _concurrency_blocked() and
        # _slot_available_event(), so acquire() can wait for a freed slot without
        # polling.
        if self._next_allowed_time is None:
            return 0.0
        return max(0.0, self._next_allowed_time - self._now(now))

    def _record_sent(self, now: float | None = None) -> None:
        now = self._now(now)
        self._last_seen = now
        self._next_allowed_time = now + self._effective_delay()
        self._active += 1

    def _record_done(self, now: float | None = None) -> None:
        if self._active > 0:
            self._active -= 1
            # One slot freed, so one waiter woken: see _Event.fire().
            self._slot_available.fire(1)

    def _wake_waiters(self) -> None:
        """Wake one waiter per free concurrency slot.

        :meth:`_record_done` wakes the waiter of the slot it frees, so this is
        for the callers that make room some other way, and for a waiter that was
        woken for a slot it turned out not to use and has to pass it on (see
        :meth:`Throttler._acquire_scope_slots`).
        """
        self._slot_available.fire(self._concurrency - self._active)

    def _concurrency_blocked(self) -> bool:
        return self._active >= self._concurrency

    def _get_load(self) -> float:
        return self._active / self._concurrency

    def _slot_available_event(self) -> Deferred[None]:
        return self._slot_available.wait()

    def _discard_slot_available_event(self, event: Deferred[None]) -> None:
        self._slot_available.discard(event)

    def get_base_delay(self) -> float:
        """Return the base delay of this scope, in seconds, i.e. the delay
        before jitter is applied to it."""
        return self._base_delay

    def set_base_delay(self, delay: float, *, only_increase: bool = True) -> None:
        """Set the base delay of this scope to *delay* seconds.

        By default it only raises the delay, to honor external hints without
        making the crawl faster than configured. Pass ``only_increase=False`` to
        also allow lowering it.
        """
        if only_increase and delay <= self._base_delay:
            return
        self._base_delay = delay

    def get_concurrency(self) -> int:
        """Return the maximum number of concurrent requests allowed for this
        scope.

        For a scope with no limit, that is :setting:`CONCURRENT_REQUESTS`, or
        :data:`sys.maxsize` if that is ``0`` too.
        """
        return self._concurrency

    def set_concurrency(self, concurrency: int) -> None:
        """Set the maximum number of concurrent requests allowed for this scope,
        ``0`` for no limit."""
        concurrency = int(concurrency)
        if concurrency < 0:
            raise ValueError(
                f"Scope concurrency must be 0 or higher, got {concurrency!r}."
            )
        self._concurrency = concurrency or self._no_limit
        self._wake_waiters()

    def _is_idle(self, now: float) -> bool:
        # A delay that has not elapsed yet would let the next request for the
        # scope go out earlier than its delay allows.
        if self._next_allowed_time is not None and self._next_allowed_time > now:
            return False
        return self._active == 0
