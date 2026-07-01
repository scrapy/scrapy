from __future__ import annotations

import datetime as dt
import logging
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

from scrapy.throttling import iter_scopes
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    import scrapy
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.throttling import ThrottlingManagerProtocol


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
    # Keep sub-second precision (a date less than a second away must not be
    # truncated to 0 and dropped); a past or present date yields no delay.
    return max(0.0, seconds_to_wait) or None


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


class BackoffMiddleware:
    """Downloader middleware that drives :ref:`backoff <backoff>` from download
    outcomes.

    It observes every response and download exception and, for those matching
    :setting:`BACKOFF_HTTP_CODES` or :setting:`BACKOFF_EXCEPTIONS` (globally or
    per :setting:`THROTTLING_SCOPES` scope), tells the :ref:`throttling manager
    <throttling>` to back off the request's scopes through its
    :meth:`~scrapy.throttling.ThrottlingManagerProtocol.back_off` API.

    See :ref:`throttling` for details.
    """

    def __init__(self, crawler: Crawler):
        # Throttling is a core, always-on subsystem: THROTTLING_MANAGER has a
        # non-None default and is instantiated before the downloader is built,
        # so crawler.throttler is always set here (the engine likewise asserts
        # it in its download path).
        assert crawler.throttler is not None
        self._throttler: ThrottlingManagerProtocol = crawler.throttler
        settings = crawler.settings
        # Union of the global backoff triggers and every per-scope override: a
        # response status (or exception type) outside it cannot trigger backoff
        # for any scope, so the scopes of such a request need not be resolved.
        # Each scope still makes the final decision via its scope manager's
        # triggers_backoff_* methods (which read the per-scope overrides).
        self._http_codes: set[int] = {
            int(code) for code in settings.getlist("BACKOFF_HTTP_CODES")
        }
        self._exceptions: tuple[type[BaseException], ...] = tuple(
            load_object(exc) if isinstance(exc, str) else exc
            for exc in settings.getlist("BACKOFF_EXCEPTIONS")
        )
        for scope_config in settings.getdict("THROTTLING_SCOPES").values():
            backoff = scope_config.get("backoff") or {}
            if "http_codes" in backoff:
                self._http_codes.update(int(code) for code in backoff["http_codes"])
            if "exceptions" in backoff:
                self._exceptions += tuple(
                    load_object(exc) if isinstance(exc, str) else exc
                    for exc in backoff["exceptions"]
                )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    @_warn_spider_arg
    def process_response(
        self,
        request: Request,
        response: Response,
        spider: scrapy.Spider | None = None,
    ) -> Response:
        if (
            response.status not in self._http_codes
            or "cached" in response.flags
            or request.meta.get("dont_throttle")
        ):
            return response
        matched = [
            scope
            for scope in iter_scopes(self._throttler.get_resolved_scopes(request))
            if self._throttler.get_scope_manager(scope).triggers_backoff_for_status(
                response.status
            )
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
            exception, self._exceptions
        ):
            return
        matched = [
            scope
            for scope in iter_scopes(self._throttler.get_resolved_scopes(request))
            if self._throttler.get_scope_manager(scope).triggers_backoff_for_exception(
                exception
            )
        ]
        if matched:
            self._throttler.back_off(matched)
        return

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
