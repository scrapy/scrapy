from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urljoin

from w3lib.url import safe_url_string

from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import HtmlResponse, Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.response import get_meta_refresh

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


def _build_redirect_request(
    source_request: Request, *, url: str, **kwargs: Any
) -> Request:
    redirect_request = source_request.replace(
        url=url,
        **kwargs,
        cls=None,
        cookies=None,
    )
    if "_scheme_proxy" in redirect_request.meta:
        source_request_scheme = urlparse_cached(source_request).scheme
        redirect_request_scheme = urlparse_cached(redirect_request).scheme
        if source_request_scheme != redirect_request_scheme:
            redirect_request.meta.pop("_scheme_proxy")
            redirect_request.meta.pop("proxy", None)
            redirect_request.meta.pop("_auth_proxy", None)
            redirect_request.headers.pop(b"Proxy-Authorization", None)
    has_cookie_header = "Cookie" in redirect_request.headers
    has_authorization_header = "Authorization" in redirect_request.headers
    if has_cookie_header or has_authorization_header:
        default_ports = {"http": 80, "https": 443}

        parsed_source_request = urlparse_cached(source_request)
        source_scheme, source_host, source_port = (
            parsed_source_request.scheme,
            parsed_source_request.hostname,
            parsed_source_request.port
            or default_ports.get(parsed_source_request.scheme),
        )

        parsed_redirect_request = urlparse_cached(redirect_request)
        redirect_scheme, redirect_host, redirect_port = (
            parsed_redirect_request.scheme,
            parsed_redirect_request.hostname,
            parsed_redirect_request.port
            or default_ports.get(parsed_redirect_request.scheme),
        )

        if has_cookie_header and (
            redirect_scheme not in {source_scheme, "https"}
            or source_host != redirect_host
        ):
            del redirect_request.headers["Cookie"]

        # https://fetch.spec.whatwg.org/#ref-for-cors-non-wildcard-request-header-name
        if has_authorization_header and (
            source_scheme != redirect_scheme
            or source_host != redirect_host
            or source_port != redirect_port
        ):
            del redirect_request.headers["Authorization"]

    return redirect_request


class BaseRedirectMiddleware:
    enabled_setting: str = "REDIRECT_ENABLED"

    def __init__(self, settings: BaseSettings):
        if not settings.getbool(self.enabled_setting):
            raise NotConfigured

        self.max_redirect_times: int = settings.getint("REDIRECT_MAX_TIMES")
        self.priority_adjust: int = settings.getint("REDIRECT_PRIORITY_ADJUST")

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings)

    def _redirect(
        self, redirected: Request, request: Request, spider: Spider, reason: Any
    ) -> Request:
        ttl = request.meta.setdefault("redirect_ttl", self.max_redirect_times)
        redirects = request.meta.get("redirect_times", 0) + 1

        if ttl and redirects <= self.max_redirect_times:
            redirected.meta["redirect_times"] = redirects
            redirected.meta["redirect_ttl"] = ttl - 1
            redirected.meta["redirect_urls"] = [
                *request.meta.get("redirect_urls", []),
                request.url,
            ]
            redirected.meta["redirect_reasons"] = [
                *request.meta.get("redirect_reasons", []),
                reason,
            ]
            redirected.dont_filter = request.dont_filter
            redirected.priority = request.priority + self.priority_adjust
            logger.debug(
                "Redirecting (%(reason)s) to %(redirected)s from %(request)s",
                {"reason": reason, "redirected": redirected, "request": request},
                extra={"spider": spider},
            )
            return redirected
        logger.debug(
            "Discarding %(request)s: max redirections reached",
            {"request": request},
            extra={"spider": spider},
        )
        raise IgnoreRequest("max redirections reached")

    def _redirect_request_using_get(
        self, request: Request, redirect_url: str
    ) -> Request:
        redirect_request = _build_redirect_request(
            request,
            url=redirect_url,
            method="GET",
            body="",
        )
        redirect_request.headers.pop("Content-Type", None)
        redirect_request.headers.pop("Content-Length", None)
        return redirect_request


class RedirectMiddleware(BaseRedirectMiddleware):
    """
    Handle redirection of requests based on response status
    and meta-refresh html tag.
    """

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Request | Response:
        if (
            request.meta.get("dont_redirect", False)
            or response.status in getattr(spider, "handle_httpstatus_list", [])
            or response.status in request.meta.get("handle_httpstatus_list", [])
            or request.meta.get("handle_httpstatus_all", False)
        ):
            return response

        allowed_status = (301, 302, 303, 307, 308)
        if "Location" not in response.headers or response.status not in allowed_status:
            return response

        assert response.headers["Location"] is not None
        location = safe_url_string(response.headers["Location"])
        if response.headers["Location"].startswith(b"//"):
            request_scheme = urlparse_cached(request).scheme
            location = request_scheme + "://" + location.lstrip("/")

        redirected_url = urljoin(request.url, location)
        redirected = _build_redirect_request(request, url=redirected_url)
        if urlparse_cached(redirected).scheme not in {"http", "https"}:
            return response

        if response.status in (301, 307, 308) or request.method == "HEAD":
            return self._redirect(redirected, request, spider, response.status)

        redirected = self._redirect_request_using_get(request, redirected_url)
        return self._redirect(redirected, request, spider, response.status)


class MetaRefreshMiddleware(BaseRedirectMiddleware):
    enabled_setting = "METAREFRESH_ENABLED"

    def __init__(self, settings: BaseSettings):
        super().__init__(settings)
        self._ignore_tags: list[str] = settings.getlist("METAREFRESH_IGNORE_TAGS")
        self._maxdelay: int = settings.getint("METAREFRESH_MAXDELAY")

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Request | Response:
        if (
            request.meta.get("dont_redirect", False)
            or request.method == "HEAD"
            or not isinstance(response, HtmlResponse)
            or urlparse_cached(request).scheme not in {"http", "https"}
        ):
            return response

        interval, url = get_meta_refresh(response, ignore_tags=self._ignore_tags)
        if not url:
            return response
        redirected = self._redirect_request_using_get(request, url)
        if urlparse_cached(redirected).scheme not in {"http", "https"}:
            return response
        if cast(float, interval) < self._maxdelay:
            return self._redirect(redirected, request, spider, "meta refresh")
        return response
