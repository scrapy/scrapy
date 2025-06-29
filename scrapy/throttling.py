from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Iterable
from datetime import UTC
from email.utils import parsedate_to_datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Protocol, TypedDict, Union
from weakref import WeakKeyDictionary

from typing_extensions import NotRequired, Self

from scrapy.http import Request, Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


def _parse_retry_after(response: Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        value = value.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    if value.isdigit():
        return float(value)  # seconds
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    now = dt.datetime.now(UTC)
    seconds_to_wait = (date - now).total_seconds()
    return max(0, int(seconds_to_wait)) or None


def _parse_ratelimit_reset(response: Response) -> float | None:
    value = response.headers.get("RateLimit-Reset")
    if not value:
        return None
    try:
        value = value.decode("utf-8").strip()
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


ScopeID = str
BackoffData = Union[None, ScopeID, Iterable[ScopeID], dict[ScopeID, BackoffScopeData]]
RequestScopes = Union[None, ScopeID, Iterable[ScopeID], dict[ScopeID, float | None]]


def iter_scopes(scopes: RequestScopes) -> Iterable[ScopeID]:
    if scopes is None:
        return ()
    if isinstance(scopes, str):
        return (scopes,)
    if isinstance(scopes, dict):
        return scopes.keys()
    return iter(scopes)


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
    if value is not None:
        if not isinstance(scopes, dict):
            if scopes is None:
                scopes = {}
            elif isinstance(scopes, str):
                scopes = {scopes: None}
            elif isinstance(scopes, Iterable):
                scopes = {s: None for s in scopes}
            else:
                raise TypeError(
                    f"Invalid type ({type(scopes)}) of scopes value "
                    f"{scopes!r}. Expected None, str, Iterable or dict."
                )
        if scope in scopes and not isinstance(scopes[scope], dict):
            raise TypeError(f"Scope {scope!r} has a non-dict value in {scopes!r}")
        scopes[scope] = value
    elif scopes is None:
        scopes = scope
    elif isinstance(scopes, str):
        if scopes != scope:
            scopes = {scopes, scope}
    elif isinstance(scopes, dict):
        if scope not in scopes:
            scopes[scope] = None
    elif isinstance(scopes, Iterable):
        if scope not in scopes:
            scopes = set(scopes) | {scope}
    else:
        raise TypeError(
            f"Invalid type ({type(scopes)}) of scopes value "
            f"{scopes!r}. Expected None, str, Iterable or dict."
        )
    return scopes


def update_scope_backoff(
    backoff: BackoffData,
    scope: ScopeID,
    /,
    *,
    delay: float | None = None,
    consumed: float | None = None,
) -> BackoffData:
    """Add *scope* to *backoff* or update its existing entry the given
    parameters.

    This is a utility function to help extending the output of
    :meth:`~ThrottlingManagerProtocol.get_initial_backoff`,
    :meth:`~ThrottlingManagerProtocol.get_response_backoff` or
    :meth:`~ThrottlingManagerProtocol.get_exception_backoff`, e.g. in
    :class:`ThrottlingManager` subclasses.
    """
    has_params = delay is not None or consumed is not None
    if has_params:
        if not isinstance(backoff, dict):
            if backoff is None:
                backoff = {}
            elif isinstance(backoff, str):
                backoff = {backoff: {}}
            elif isinstance(backoff, Iterable):
                backoff = {s: {} for s in backoff}
            else:
                raise TypeError(
                    f"Invalid type ({type(backoff)}) of scopes value "
                    f"{backoff!r}. Expected None, str, Iterable or dict."
                )
        if scope in backoff:
            if not isinstance(backoff[scope], dict):
                raise TypeError(f"Scope {scope!r} has a non-dict value in {backoff!r}")
        else:
            backoff[scope] = {}
        if delay is not None:
            backoff[scope]["delay"] = delay
        if consumed is not None:
            backoff[scope]["consumed"] = consumed
    elif backoff is None:
        backoff = scope
    elif isinstance(backoff, str):
        if backoff != scope:
            backoff = {backoff, scope}
    elif isinstance(backoff, dict):
        if scope not in backoff:
            backoff[scope] = {}
    elif isinstance(backoff, Iterable):
        if scope not in backoff:
            backoff = set(backoff) | {scope}
    else:
        raise TypeError(
            f"Invalid type ({type(backoff)}) of scopes value "
            f"{backoff!r}. Expected None, str, Iterable or dict."
        )
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


GetScopesMethod = Callable[
    [ThrottlingManagerProtocol, Request], Awaitable[RequestScopes]
]


def scope_cache(f: GetScopesMethod) -> GetScopesMethod:
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
    cache = WeakKeyDictionary()

    @wraps(f)
    async def wrapper(self, request: Request):
        if request in cache:
            return cache[request]
        scopes = await f(self, request)
        cache[request] = scopes
        return scopes

    return wrapper


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
        self.throttler = crawler.throttler
        self.backoff_http_codes = set(crawler.settings.getlist("BACKOFF_HTTP_CODES"))
        self.backoff_exceptions = tuple(
            load_object(cls) for cls in crawler.settings.getlist("BACKOFF_EXCEPTIONS")
        )

    @scope_cache
    async def get_scopes(
        self: ThrottlingManagerProtocol, request: Request
    ) -> RequestScopes:
        return urlparse_cached(request).netloc

    async def get_initial_backoff(self) -> BackoffData:
        return None

    async def get_response_backoff(self, response: Response) -> BackoffData:
        if response.status not in self.backoff_http_codes:
            return None
        assert response.request is not None
        assert self.throttler is not None
        scopes = await self.throttler.get_scopes(response.request)
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
        if isinstance(exception, self.backoff_exceptions):
            assert self.throttler is not None
            return await self.throttler.get_scopes(request)
        return None


class ThrottlingScopeManagerProtocol(Protocol):
    """A protocol for :setting:`THROTTLING_SCOPE_MANAGER` :ref:`components
    <topics-components>`.

    The ``__init__`` method gets a ``config`` dict with the base configuration
    of the managed throttling scope. For example:

    .. code-block:: python

        {
            "id": "example.com",
            "concurrency": 1.0,
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
                "concurrency_factor": 0.8,
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


class ThrottlingScopeManager:
    """The default :setting:`THROTTLING_SCOPE_MANAGER` class."""
