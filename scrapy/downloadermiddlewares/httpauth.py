"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from w3lib.http import basic_auth_header

from scrapy import Request, Spider, signals
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.url import url_is_from_any_domain

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response


_NO_PORT = object()
_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
}


def _origin(request: Request) -> str:
    parsed_url = urlparse_cached(request)
    scheme = parsed_url.scheme
    netloc = (
        parsed_url.netloc
        if parsed_url.port != _DEFAULT_PORTS[scheme]
        else parsed_url.hostname
    )
    return f"{scheme}://{netloc}"


def _setdefault_auth_origin(request: Request) -> str:
    if origin := request.meta.get("auth_origin"):
        return origin
    origin = _origin(request)
    request.meta["auth_origin"] = origin
    return origin


class HttpAuthMiddleware:
    """Set Basic HTTP Authorization header
    (http_user and http_pass spider class attributes)"""

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls()
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def __init__(self):
        self.auth = None
        self.domain = None

    def spider_opened(self, spider: Spider) -> None:
        usr = getattr(spider, "http_user", "")
        pwd = getattr(spider, "http_pass", "")
        if usr or pwd:
            self.auth = basic_auth_header(usr, pwd)
            self.domain = spider.http_auth_domain  # type: ignore[attr-defined]

    def process_request(
        self, request: Request, spider: Spider
    ) -> Request | Response | None:
        if (
            b"Authorization" in request.headers
            or urlparse_cached(request).scheme not in _DEFAULT_PORTS
        ):
            return None
        user = request.meta.get("http_user", "")
        password = request.meta.get("http_pass", "")
        if user or password:
            auth_origin = _setdefault_auth_origin(request)
            request_origin = _origin(request)
            if auth_origin == request_origin:
                auth = basic_auth_header(user, password)
            else:
                auth = None
        elif not self.domain or url_is_from_any_domain(request.url, [self.domain]):
            auth = self.auth
        else:
            auth = None
        if auth:
            request.headers[b"Authorization"] = auth
        return None
