from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy.exceptions import NotConfigured
from scrapy.throttler import iter_scopes
from scrapy.utils._headers import _parse_ratelimit_reset, _parse_retry_after
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.misc import _load_objects

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    import scrapy
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.throttler import ThrottlerProtocol


logger = logging.getLogger(__name__)


class BackoffMiddleware:
    """Downloader middleware that drives :ref:`backoff <backoff>` from download
    outcomes.

    It observes every response and download exception and, for those matching
    :setting:`BACKOFF_HTTP_CODES` or :setting:`BACKOFF_EXCEPTIONS` (globally or
    per :setting:`THROTTLING_SCOPES` scope), tells the :ref:`throttler
    <throttling>` to back off the request's scopes through its
    :meth:`~scrapy.throttler.ThrottlerProtocol.back_off` API.

    It is enabled by default; set :setting:`BACKOFF_ENABLED` to ``False`` to
    disable it without removing it from :setting:`DOWNLOADER_MIDDLEWARES`.

    See :ref:`throttling` for details.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("BACKOFF_ENABLED"):
            raise NotConfigured
        assert crawler.throttler is not None
        self._throttler: ThrottlerProtocol = crawler.throttler
        settings = crawler.settings
        self._http_codes: set[int] = {
            int(code) for code in settings.getlist("BACKOFF_HTTP_CODES")
        }
        self._exceptions: tuple[type[BaseException], ...] = _load_objects(
            settings.getlist("BACKOFF_EXCEPTIONS")
        )
        # Per-scope overrides; a scope absent from these uses the globals above.
        self._scope_http_codes: dict[str, set[int]] = {}
        self._scope_exceptions: dict[str, tuple[type[BaseException], ...]] = {}
        # Unions of the globals and every per-scope override, used as a cheap
        # pre-filter to skip outcomes that no scope backs off on.
        self._any_http_codes: set[int] = set(self._http_codes)
        self._any_exceptions: tuple[type[BaseException], ...] = self._exceptions
        for scope_id, scope_config in settings.getdict("THROTTLING_SCOPES").items():
            backoff = scope_config.get("backoff") or {}
            if "http_codes" in backoff:
                codes = {int(code) for code in backoff["http_codes"]}
                self._scope_http_codes[scope_id] = codes
                self._any_http_codes |= codes
            if "exceptions" in backoff:
                exceptions = _load_objects(backoff["exceptions"])
                self._scope_exceptions[scope_id] = exceptions
                self._any_exceptions += exceptions

    @_warn_spider_arg
    def process_response(
        self,
        request: Request,
        response: Response,
        spider: scrapy.Spider | None = None,
    ) -> Response:
        if (
            response.status not in self._any_http_codes
            or "cached" in response.flags
            or request.meta.get("dont_throttle")
        ):
            return response
        matched = [
            scope
            for scope in iter_scopes(self._throttler.get_resolved_scopes(request))
            if response.status in self._scope_http_codes.get(scope, self._http_codes)
        ]
        if matched:
            self._throttler.back_off(matched, delay=self._response_delay(response))
        return response

    @_warn_spider_arg
    def process_exception(
        self,
        request: Request,
        exception: Exception,
        spider: scrapy.Spider | None = None,
    ) -> None:
        if request.meta.get("dont_throttle") or not isinstance(
            exception, self._any_exceptions
        ):
            return
        matched = [
            scope
            for scope in iter_scopes(self._throttler.get_resolved_scopes(request))
            if isinstance(
                exception, self._scope_exceptions.get(scope, self._exceptions)
            )
        ]
        if matched:
            self._throttler.back_off(matched)

    @staticmethod
    def _response_delay(response: Response) -> float | None:
        """Return the hard minimum delay requested by *response* through a
        ``Retry-After`` or ``RateLimit-Reset`` header, or ``None``."""
        delays = [
            delay
            for delay in (
                _parse_retry_after(response),
                _parse_ratelimit_reset(response),
            )
            if delay is not None
        ]
        return max(delays) if delays else None
