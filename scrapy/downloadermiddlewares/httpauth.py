"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from w3lib.http import basic_auth_header

from scrapy import Request, Spider, signals
from scrapy.crawler import Crawler
from scrapy.http import Response
from scrapy.utils.url import url_is_from_any_domain

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


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
    ) -> Union[Request, Response, None]:
        if b"Authorization" in request.headers:
            return None
        usr = request.meta.get("http_user", "")
        pwd = request.meta.get("http_pass", "")
        if usr or pwd:
            auth = basic_auth_header(usr, pwd)
        elif not self.domain or url_is_from_any_domain(request.url, [self.domain]):
            auth = self.auth
        else:
            auth = None
        if auth:
            request.headers[b"Authorization"] = auth
        return None
