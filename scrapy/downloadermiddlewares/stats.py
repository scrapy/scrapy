from __future__ import annotations

from typing import TYPE_CHECKING

from twisted.web import http

from scrapy.exceptions import NotConfigured
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.python import global_object_name, to_bytes
from scrapy.utils.request import request_httprepr

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.statscollectors import StatsCollector


def get_header_size(
    headers: dict[str, list[str | bytes] | tuple[str | bytes, ...]],
) -> int:
    size = 0
    for key, value in headers.items():
        if isinstance(value, (list, tuple)):
            for v in value:
                size += len(b": ") + len(key) + len(v)
    return size + len(b"\r\n") * (len(headers.keys()) - 1)


def get_status_size(response_status: int) -> int:
    return len(to_bytes(http.RESPONSES.get(response_status, b""))) + 15
    # resp.status + b"\r\n" + b"HTTP/1.1 <100-599> "


class DownloaderStats:
    def __init__(self, stats: StatsCollector):
        self.stats: StatsCollector = stats

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("DOWNLOADER_STATS"):
            raise NotConfigured
        assert crawler.stats
        return cls(crawler.stats)

    @_warn_spider_arg
    def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> Request | Response | None:
        self.stats.inc_value("downloader/request_count")
        self.stats.inc_value(f"downloader/request_method_count/{request.method}")
        reqlen = len(request_httprepr(request))
        self.stats.inc_value("downloader/request_bytes", reqlen)
        return None

    @_warn_spider_arg
    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Request | Response:
        self.stats.inc_value("downloader/response_count")
        self.stats.inc_value(f"downloader/response_status_count/{response.status}")
        reslen = (
            len(response.body)
            + get_header_size(response.headers)
            + get_status_size(response.status)
            + 4
        )
        # response.body + b"\r\n"+ response.header + b"\r\n" + response.status
        self.stats.inc_value("downloader/response_bytes", reslen)
        return response

    @_warn_spider_arg
    def process_exception(
        self, request: Request, exception: Exception, spider: Spider | None = None
    ) -> Request | Response | None:
        ex_class = global_object_name(exception.__class__)
        self.stats.inc_value("downloader/exception_count")
        self.stats.inc_value(f"downloader/exception_type_count/{ex_class}")
        return None
