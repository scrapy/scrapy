from __future__ import annotations

import contextlib
import datetime as dt
import logging
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from email.utils import parsedate_to_datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, TypeVar, cast
from weakref import WeakKeyDictionary

from twisted.internet.defer import Deferred
from typing_extensions import NotRequired, Self

from scrapy import signals
from scrapy.utils.asyncio import sleep, wait_for_first
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response


logger = logging.getLogger(__name__)


def _parse_retry_after(response: Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    if value.isdigit():
        return float(value)  # seconds
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    seconds_to_wait = (date - now).total_seconds()
    return max(0, int(seconds_to_wait)) or None


def _parse_ratelimit_reset(response: Response) -> float | None:
    raw = response.headers.get("RateLimit-Reset")
    if not raw:
        return None
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class BackoffScopeData(TypedDict):
    delay: NotRequired[float]
    consumed: NotRequired[float]
    remaining: NotRequired[float]


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


class ThrottlingScopeConfig(TypedDict, total=False):
    """Accepted keys of :setting:`THROTTLING_SCOPES` entries.

    Every key is optional; missing keys fall back to the matching global
    setting (e.g. ``delay`` falls back to :setting:`DOWNLOAD_DELAY`).
    """

    concurrency: int

    min_concurrency: int
    """Floor. Never drop below this during backoff/rampup."""

    delay: float
    jitter: float | list[float]
    quota: float
    window: float
    rampup: bool

    manager: str | type
    """Import path or class of a custom :setting:`THROTTLING_SCOPE_MANAGER` for
    this scope."""

    backoff: BackoffConfig


ScopeID = str
BackoffData = None | ScopeID | Iterable[ScopeID] | dict[ScopeID, BackoffScopeData]
RequestScopes = None | ScopeID | Iterable[ScopeID] | dict[ScopeID, float | None]


def iter_scopes(scopes: RequestScopes) -> Iterable[ScopeID]:
    if scopes is None:
        return ()
    if isinstance(scopes, str):
        return (scopes,)
    if isinstance(scopes, dict):
        return scopes.keys()
    return iter(scopes)


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


def _to_scope_dict(collection: Any, default: Callable[[], Any]) -> dict[ScopeID, Any]:
    """Normalize *collection* (``None``, str, iterable or dict) into a dict
    mapping scope names to values produced by *default*."""
    if isinstance(collection, dict):
        return collection
    if collection is None:
        return {}
    if isinstance(collection, str):
        return {collection: default()}
    if isinstance(collection, Iterable):
        return {scope: default() for scope in collection}
    raise TypeError(
        f"Invalid type ({type(collection)}) of scopes value "
        f"{collection!r}. Expected None, str, Iterable or dict."
    )


def _add_bare_scope(collection: Any, scope: ScopeID, empty: Any) -> Any:
    """Add *scope* to *collection* without any associated value, keeping the
    most compact representation possible."""
    if collection is None:
        return scope
    if isinstance(collection, str):
        return collection if collection == scope else {collection, scope}
    if isinstance(collection, dict):
        if scope not in collection:
            collection[scope] = empty
        return collection
    if isinstance(collection, Iterable):
        return set(collection) | {scope} if scope not in collection else collection
    raise TypeError(
        f"Invalid type ({type(collection)}) of scopes value "
        f"{collection!r}. Expected None, str, Iterable or dict."
    )


def add_scope(
    scopes: RequestScopes,
    scope: ScopeID,
    value: float | None = None,
    /,
) -> RequestScopes:
    """Add *scope* to *scopes* with *value*.

    This is a utility function to help extending the output of
    :meth:`~ThrottlingManagerProtocol.get_scopes`, e.g. in
    :class:`ThrottlingManager` subclasses.
    """
    if value is None:
        return cast("RequestScopes", _add_bare_scope(scopes, scope, None))
    scopes = _to_scope_dict(scopes, lambda: None)
    if scope in scopes and not isinstance(scopes[scope], dict):
        raise TypeError(f"Scope {scope!r} has a non-dict value in {scopes!r}")
    scopes[scope] = value
    return scopes


def update_scope_backoff(
    backoff: BackoffData,
    scope: ScopeID,
    /,
    *,
    delay: float | None = None,
    consumed: float | None = None,
) -> BackoffData:
    """Add *scope* to *backoff* or update its existing entry with the given
    parameters.

    This is a utility function to help extending the output of
    :meth:`~ThrottlingManagerProtocol.get_initial_backoff`,
    :meth:`~ThrottlingManagerProtocol.get_response_backoff` or
    :meth:`~ThrottlingManagerProtocol.get_exception_backoff`, e.g. in
    :class:`ThrottlingManager` subclasses.
    """
    if delay is None and consumed is None:
        return cast("BackoffData", _add_bare_scope(backoff, scope, {}))
    backoff = _to_scope_dict(backoff, dict)
    entry = backoff.setdefault(scope, {})
    if not isinstance(entry, dict):
        raise TypeError(f"Scope {scope!r} has a non-dict value in {backoff!r}")
    if delay is not None:
        entry["delay"] = delay
    if consumed is not None:
        entry["consumed"] = consumed
    return backoff


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

    async def get_initial_backoff(self) -> BackoffData:
        """Return the initial throttling data.

        This method is called before the first request is sent, and it should
        be used to provide an initial throttling state, to be used before it is
        updated with later calls to :meth:`get_response_backoff` and
        :meth:`get_exception_backoff`.

        **Return values:**

        You may return any of the following:

        -   ``None``: no throttling data to report.

        -   A string: a single scope name, indicating that the scope is
            currently exhausted.

        -   An iterable of strings: multiple scope names, indicating that
            those scopes are currently exhausted.

        -   A dict with scope names as keys and dict values. Dict values
            support the following keys:

            -   ``"delay"``: a float indicating how many seconds to wait before
                sending another request for the scope.

            -   ``"quota"``: a float indicating the remaining :ref:`throttling
                quota <throttling-quotas>`.

            If ``"quota"`` is not specified, the resource is considered
            exhausted.

        For example:

        .. code-block:: python

            return {
                "scope1": {"delay": 5.0},
                "scope2": {},
                "scope3": {"quota": 42.0},
            }
        """

    async def get_response_backoff(self, response: Response) -> BackoffData:
        """Return a throttling data update based on *response*.

        It supports the same return values as :meth:`get_initial_backoff`.
        """

    async def get_exception_backoff(
        self, request: Request, exception: Exception
    ) -> BackoffData:
        """Return a throttling data update based on *exception* and the
        *request* that caused it.

        It supports the same return values as :meth:`get_initial_backoff`.
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
        used by a :ref:`throttling-aware scheduler <throttling-aware-scheduler>`
        to decide whether a request can be dequeued now. It assumes the scopes
        of *request* have already been resolved (e.g. by an earlier
        :meth:`get_scopes` call at enqueue time).
        """

    def reserve(self, request: Request) -> None:
        """Claim a send for *request*: record the send on every one of its
        scopes and mark *request* as reserved, so that a later :meth:`acquire`
        for it returns immediately without reserving again.

        A :ref:`throttling-aware scheduler <throttling-aware-scheduler>` calls
        this when it decides to dequeue *request* (after :meth:`is_ready`
        returned ``True``). The reservation is released by :meth:`release`.
        """

    def time_until_ready(self, request: Request) -> float | None:
        """Return the number of seconds until every time-based gate of
        *request* would be open, or ``None`` if no time-based gate is currently
        blocking it (only a concurrency slot could be).

        Used by a :ref:`throttling-aware scheduler
        <throttling-aware-scheduler>` to schedule a wakeup when all pending
        requests are time-blocked.
        """

    def scope_load(self, scope_id: str) -> float:
        """Return the current load of the scope identified by *scope_id*: its
        active sends divided by its concurrency limit (or by the global
        :setting:`CONCURRENT_REQUESTS` when the scope has no explicit limit).

        Used by a :ref:`throttling-aware scheduler
        <throttling-aware-scheduler>` to balance dequeuing across scopes,
        preferring the least-loaded ones.
        """

    async def process_response(self, response: Response) -> None:
        """Update the throttling state based on *response*."""

    async def process_exception(self, request: Request, exception: Exception) -> None:
        """Update the throttling state based on a download *exception*."""


_GetScopesMethod = TypeVar(
    "_GetScopesMethod", bound=Callable[..., Awaitable[RequestScopes]]
)


def scope_cache(f: _GetScopesMethod) -> _GetScopesMethod:
    """Decorator to cache the result of
    :meth:`~ThrottlingManagerProtocol.get_scopes` calls.

    It should be used so that calls to
    :meth:`~ThrottlingManagerProtocol.get_scopes` from methods like
    :meth:`~ThrottlingManagerProtocol.get_response_backoff` or
    :meth:`~ThrottlingManagerProtocol.get_exception_backoff` do not become
    unnecessarily expensive.

    For example:

    .. code-block:: python

        from scrapy.utils.httpobj import urlparse_cached
        from scrapy.utils.throttling import scope_cache


        class MyThrottlingManager:
            @scope_cache
            async def get_scopes(self, request):
                return urlparse_cached(request).netloc
    """

    @wraps(f)
    async def wrapper(self: Any, request: Request) -> RequestScopes:
        cache: WeakKeyDictionary[Request, RequestScopes] | None = self.__dict__.get(
            "_scope_cache"
        )
        if cache is None:
            cache = self.__dict__["_scope_cache"] = WeakKeyDictionary()
        if request in cache:
            return cache[request]
        scopes = await f(self, request)
        cache[request] = scopes
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
        self._backoff_http_codes = {
            int(code) for code in crawler.settings.getlist("BACKOFF_HTTP_CODES")
        }
        self._backoff_exceptions = tuple(
            load_object(cls) for cls in crawler.settings.getlist("BACKOFF_EXCEPTIONS")
        )
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
        self._scopes_config: dict[str, dict[str, Any]] = crawler.settings.getdict(
            "THROTTLING_SCOPES"
        )
        self._scope_managers: dict[ScopeID, ThrottlingScopeManagerProtocol] = {}
        self._global_concurrency: int = crawler.settings.getint("CONCURRENT_REQUESTS")
        self._last_eviction: float | None = None
        # Concurrency slots reserved by acquire(), to be released once the
        # request finishes downloading.
        self._reserved: WeakKeyDictionary[
            Request, list[tuple[ThrottlingScopeManagerProtocol, float | None]]
        ] = WeakKeyDictionary()

    @scope_cache
    async def get_scopes(self, request: Request) -> RequestScopes:
        return self._resolve_scopes_sync(request)

    def _resolve_scopes_sync(self, request: Request) -> RequestScopes:
        """Best-effort synchronous scope resolution.

        It mirrors :meth:`get_scopes`, and is used by the synchronous
        readiness methods (:meth:`is_ready`, :meth:`reserve`,
        :meth:`time_until_ready`) when the cached result of an earlier
        :meth:`get_scopes` call is not available (e.g. for a request restored
        from disk). Subclasses whose :meth:`get_scopes` cannot be resolved
        synchronously should rely on the enqueue-time cache instead.
        """
        scopes = request.meta.get("throttling_scopes")
        if scopes is not None:
            return cast("RequestScopes", scopes)
        return urlparse_cached(request).netloc

    def _cached_scope_values(
        self, request: Request
    ) -> list[tuple[ScopeID, float | None]]:
        """Return the ``(scope_id, quota_amount)`` pairs of *request*, reading
        the cache populated by :meth:`get_scopes` and falling back to
        :meth:`_resolve_scopes_sync`."""
        cache: WeakKeyDictionary[Request, RequestScopes] | None = self.__dict__.get(
            "_scope_cache"
        )
        scopes = cache.get(request) if cache is not None else None
        if scopes is None:
            scopes = self._resolve_scopes_sync(request)
        return list(iter_scope_values(scopes))

    async def get_initial_backoff(self) -> BackoffData:
        return None

    async def get_response_backoff(self, response: Response) -> BackoffData:
        assert response.request is not None
        if response.request.meta.get("throttling_dont_track"):
            return None
        if response.status not in self._backoff_http_codes:
            return None
        scopes = await self.get_scopes(response.request)
        if delay := self.get_response_delay(response):
            scopes = {scope: {"delay": delay} for scope in iter_scopes(scopes)}
        return scopes

    def get_response_delay(self, response: Response) -> float | None:
        """Return the throttling delay requested by the response."""
        retry_after = _parse_retry_after(response)
        ratelimit_reset = _parse_ratelimit_reset(response)
        if retry_after is None and ratelimit_reset is None:
            return None
        if retry_after is not None and ratelimit_reset is not None:
            return max(retry_after, ratelimit_reset)
        if retry_after is not None:
            return retry_after
        assert ratelimit_reset is not None
        return ratelimit_reset

    async def get_exception_backoff(
        self, request: Request, exception: Exception
    ) -> BackoffData:
        if request.meta.get("throttling_dont_track"):
            return None
        if isinstance(exception, self._backoff_exceptions):
            return await self.get_scopes(request)
        return None

    # -- Scope-state coordination (called from the request lifecycle) --------

    def _get_scope_manager(self, scope_id: ScopeID) -> ThrottlingScopeManagerProtocol:
        manager = self._scope_managers.get(scope_id)
        if manager is None:
            config: dict[str, Any] = dict(self._scopes_config.get(scope_id, {}))
            config.setdefault("id", scope_id)
            manager_cls = (
                load_object(config["manager"])
                if "manager" in config
                else self._default_scope_manager_cls
            )
            manager = build_from_crawler(manager_cls, self.crawler, config)
            self._scope_managers[scope_id] = manager
        return manager

    async def acquire(self, request: Request) -> None:
        # A throttling-aware scheduler reserves the request before handing it
        # to the engine, so there is nothing left to wait for or record here.
        if request in self._reserved:
            return
        now = time.monotonic()
        self._maybe_evict(now)
        await self._apply_request_delay(request)
        scope_values = list(iter_scope_values(await self.get_scopes(request)))
        if not scope_values:
            return
        managers = [
            (self._get_scope_manager(scope_id), value)
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
                for manager, value in managers:
                    manager.record_sent(amount=value)
                self._reserved[request] = managers
                return
            if self._debug:
                logger.debug(
                    f"Throttling {request} until a concurrency slot frees up "
                    f"(scopes: {[scope_id for scope_id, _ in scope_values]})"
                )
            await self._wait_for_slot(blocked)

    def release(self, request: Request) -> None:
        managers = self._reserved.pop(request, None)
        if not managers:
            return
        for manager, _ in managers:
            manager.record_done()

    # -- Synchronous readiness API (used by a throttling-aware scheduler) ------

    def is_ready(self, request: Request) -> bool:
        now = time.monotonic()
        for scope_id, value in self._cached_scope_values(request):
            manager = self._get_scope_manager(scope_id)
            if manager.can_send(now=now, amount=value) > 0:
                return False
            if manager.concurrency_blocked():
                return False
        return True

    def reserve(self, request: Request) -> None:
        managers = [
            (self._get_scope_manager(scope_id), value)
            for scope_id, value in self._cached_scope_values(request)
        ]
        for manager, value in managers:
            manager.record_sent(amount=value)
        self._reserved[request] = managers

    def time_until_ready(self, request: Request) -> float | None:
        now = time.monotonic()
        wait = 0.0
        for scope_id, value in self._cached_scope_values(request):
            manager = self._get_scope_manager(scope_id)
            wait = max(wait, manager.can_send(now=now, amount=value))
        return wait if wait > 0 else None

    def scope_load(self, scope_id: ScopeID) -> float:
        manager = self._get_scope_manager(scope_id)
        active: int = getattr(manager, "_active", 0)
        concurrency: int | None = getattr(manager, "_concurrency", None)
        limit = concurrency if concurrency is not None else self._global_concurrency
        if not limit:
            return 0.0
        return active / limit

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

    async def _apply_request_delay(self, request: Request) -> None:
        """Honor the :reqmeta:`throttling_delay` meta key by holding *request*
        for the requested number of seconds the first time it is processed."""
        delay = request.meta.get("throttling_delay")
        if not delay or request.meta.get("_throttling_delayed"):
            return
        request.meta["_throttling_delayed"] = True
        if self._debug:
            logger.debug(f"Holding {request} for {delay:.2f}s (throttling_delay)")
        await sleep(float(delay))

    async def process_response(self, response: Response) -> None:
        data = await self.get_response_backoff(response)
        self._apply_backoff(data)

    async def process_exception(self, request: Request, exception: Exception) -> None:
        data = await self.get_exception_backoff(request, exception)
        self._apply_backoff(data)

    def _apply_backoff(self, data: BackoffData) -> None:
        if data is None:
            return
        if isinstance(data, dict):
            items: Iterable[tuple[ScopeID, Any]] = data.items()
        else:
            items = ((scope_id, None) for scope_id in iter_scopes(data))
        for scope_id, entry in items:
            manager = self._get_scope_manager(scope_id)
            delay = consumed = remaining = None
            if isinstance(entry, dict):
                delay = entry.get("delay")
                consumed = entry.get("consumed")
                remaining = entry.get("remaining")
            # A dict entry that only reports quota usage reconciles the quota
            # without counting as a backoff trigger.
            quota_only = (
                isinstance(entry, dict)
                and delay is None
                and (consumed is not None or remaining is not None)
            )
            if consumed is not None or remaining is not None:
                manager.reconcile_quota(consumed=consumed, remaining=remaining)
            if quota_only:
                continue
            if self._debug:
                logger.debug(f"Backoff for scope {scope_id} (delay: {delay})")
            manager.record_backoff(delay=delay)

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
            self.apply_robots_crawl_delay(urlparse_cached(request).netloc, delay)

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
        manager = self._get_scope_manager(scope_id)
        manager.set_base_delay(capped)
        manager.set_concurrency(1)

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
                "delay_factor": 0.8,
                "min_delay": 0.05,
            },
        }

    """

    @classmethod
    def from_crawler(cls, crawler: Crawler, config: dict[str, Any]) -> Self:
        return cls(crawler, config)

    def __init__(self, crawler: Crawler, config: dict[str, Any]) -> None:
        pass

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
        self, delay: float | None = None, now: float | None = None
    ) -> None:
        """Apply a backoff to this scope.

        *delay*, when given, is a hard minimum delay in seconds (e.g. from a
        ``Retry-After`` header). When omitted, an exponential backoff step is
        applied instead.
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

    def set_base_delay(self, delay: float) -> None:
        """Raise the base (non-backoff) delay of this scope to *delay* seconds.

        It never lowers the configured base delay; it is used to honor external
        hints such as a robots.txt ``Crawl-delay`` directive.
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

    -   A base :setting:`DOWNLOAD_DELAY`-style delay (``0`` by default, taken
        from the scope ``"delay"`` config) is enforced between consecutive
        requests for the scope.

    -   On a backoff trigger (a :setting:`BACKOFF_HTTP_CODES` response or a
        :setting:`BACKOFF_EXCEPTIONS` exception) the delay grows exponentially
        by :setting:`BACKOFF_DELAY_FACTOR`, bounded by :setting:`BACKOFF_MIN_DELAY`
        and :setting:`BACKOFF_MAX_DELAY`, with :setting:`BACKOFF_JITTER` applied.
        A ``Retry-After`` / ``RateLimit-Reset`` delay is honored as a hard
        minimum (capped at :setting:`BACKOFF_MAX_DELAY`).

    -   After :setting:`BACKOFF_WINDOW` seconds without a new trigger, the delay
        recovers one step at a time back towards the base delay.

    -   When the scope is configured with a ``"concurrency"`` limit (or with
        ``"rampup"``), no more than that many requests are allowed in flight at
        once, never dropping below the ``"min_concurrency"`` floor.

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
        self._base_delay: float = float(config.get("delay", 0.0))
        self._randomize: bool = bool(
            config.get("randomize_delay", settings.getbool("RANDOMIZE_DOWNLOAD_DELAY"))
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
        self._jitter: float | list[float] = backoff.get(
            "jitter", settings.getfloat("BACKOFF_JITTER")
        )
        self._window: float = settings.getfloat("BACKOFF_WINDOW")
        self._min_concurrency: int = int(config.get("min_concurrency", 1))

        # Rampup.
        rampup = config.get("rampup")
        self._rampup_enabled: bool = bool(rampup)
        rampup_config: dict[str, Any] = rampup if isinstance(rampup, dict) else {}
        self._rampup_target: tuple[float, float] = self._parse_target(
            rampup_config.get("backoff_target", settings.get("RAMPUP_BACKOFF_TARGET"))
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
            self._concurrency = self._min_concurrency
        else:
            self._concurrency = None

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
    def _parse_target(value: Any) -> tuple[float, float]:
        if isinstance(value, (list, tuple)):
            return float(value[0]), float(value[1])
        return float(value), float(value)

    def _apply_jitter(self, value: float) -> float:
        if isinstance(self._jitter, (list, tuple)):
            low, high = self._jitter[0], self._jitter[1]
            return value * (1 + random.uniform(low, high))  # noqa: S311
        if not self._jitter:
            return value
        return value * random.uniform(1 - self._jitter, 1 + self._jitter)  # noqa: S311

    def _effective_delay(self) -> float:
        if self._backoff_level == 0 and self._randomize and self._delay > 0:
            return random.uniform(0.5 * self._delay, 1.5 * self._delay)  # noqa: S311
        return self._delay

    def _recover(self, now: float) -> None:
        if self._backoff_level == 0 or self._last_backoff_time is None:
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
        if self._rampup_window_start is None:
            self._rampup_window_start = now
            return
        while now - self._rampup_window_start >= self._window:
            self._rampup_window_start += self._window
            if self._rampup_backoffs < self._rampup_target[0]:
                self._rampup_step()
            self._rampup_backoffs = 0

    def _rampup_step(self) -> None:
        # Backoff in progress: let it recover before probing again.
        if self._backoff_level > 0:
            return
        if self._delay > self._rampup_min_delay:
            self._delay = max(
                self._rampup_min_delay, self._delay * self._rampup_delay_factor
            )
            self._base_delay = min(self._base_delay, self._delay)
        elif self._concurrency is not None:
            self._concurrency += 1

    def _maybe_reset_quota(self, now: float) -> None:
        if self._quota is None:
            return
        if self._quota_window_start is None:
            self._quota_window_start = now
            return
        while now - self._quota_window_start >= self._quota_window:
            self._quota_window_start += self._quota_window
            self._consumed = 0.0

    def can_send(self, now: float | None = None, amount: float | None = None) -> float:
        now = self._now(now)
        self._recover(now)
        self._maybe_rampup(now)
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
        self, delay: float | None = None, now: float | None = None
    ) -> None:
        now = self._now(now)
        self._last_seen = now
        self._last_backoff_time = now
        self._backoff_level += 1
        self._rampup_backoffs += 1
        if delay is not None:
            hard = min(float(delay), self._max_delay)
            self._in_backoff_until = now + hard
            self._delay = min(max(self._delay, hard, self._min_delay), self._max_delay)
        else:
            grown = (
                self._delay * self._delay_factor if self._delay > 0 else self._min_delay
            )
            grown = max(self._min_delay, grown)
            grown = min(grown, self._max_delay)
            self._delay = min(self._apply_jitter(grown), self._max_delay)
        self._next_allowed_time = now + self._delay

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

    def set_base_delay(self, delay: float) -> None:
        if delay <= self._base_delay:
            return
        self._base_delay = delay
        if self._backoff_level == 0:
            self._delay = delay

    def set_concurrency(self, concurrency: int) -> None:
        self._concurrency = max(self._min_concurrency, int(concurrency))
        self._fire_slot_waiters()

    def is_idle(self, now: float, max_idle: float) -> bool:
        if self._in_backoff_until is not None and self._in_backoff_until > now:
            return False
        if self._active > 0:
            return False
        if self._last_seen is None:
            return True
        return (now - self._last_seen) > max_idle
