"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from w3lib.http import basic_auth_header

from scrapy import Request, Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import SETTINGS_PRIORITIES
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.url import url_is_from_any_domain

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response


class HttpAuthMiddleware:
    """Set Basic HTTP Authorization header."""

    def __init__(self) -> None:
        self._auth: bytes | None = None
        self._domain: str | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls()
        usr = crawler.settings.get("HTTPAUTH_USER", "")
        pwd = crawler.settings.get("HTTPAUTH_PASS", "")
        if usr or pwd:
            domain_priority = crawler.settings.getpriority("HTTPAUTH_DOMAIN") or 0
            if domain_priority <= SETTINGS_PRIORITIES["default"]:
                raise ValueError(
                    "HTTPAUTH_DOMAIN must be set when HTTPAUTH_USER or HTTPAUTH_PASS "
                    "is configured. Set it to a domain (e.g. 'example.com') to restrict "
                    "credentials to that domain, or set it to None to send credentials "
                    "with all requests."
                )
            o._auth = basic_auth_header(usr, pwd)
            o._domain = crawler.settings.get("HTTPAUTH_DOMAIN")
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider: Spider) -> None:
        usr = getattr(spider, "http_user", "")
        pwd = getattr(spider, "http_pass", "")
        if usr or pwd:
            warnings.warn(
                "Use the HTTPAUTH_USER, HTTPAUTH_PASS, and HTTPAUTH_DOMAIN settings "
                "instead of the http_user, http_pass, and http_auth_domain spider "
                "attributes. Support for the spider attributes will be removed in a "
                "future version of Scrapy.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
            self._auth = basic_auth_header(usr, pwd)
            self._domain = spider.http_auth_domain  # type: ignore[attr-defined]

    @_warn_spider_arg
    def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> Request | Response | None:
        if b"Authorization" in request.headers:
            return None
        # Per-request meta overrides
        usr = request.meta.get("http_user", "")
        pwd = request.meta.get("http_pass", "")
        if usr or pwd:
            domain = request.meta.get("http_auth_domain")
            if not domain or url_is_from_any_domain(request.url, [domain]):
                request.headers[b"Authorization"] = basic_auth_header(usr, pwd)
            return None
        # Middleware-level auth
        if self._auth and (
            not self._domain or url_is_from_any_domain(request.url, [self._domain])
        ):
            request.headers[b"Authorization"] = self._auth
        return None
