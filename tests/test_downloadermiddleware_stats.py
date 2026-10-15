from __future__ import annotations

import pytest

from scrapy.downloadermiddlewares.stats import DownloaderStats, get_header_size
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler


class MyException(Exception):
    pass


class TestDownloaderStats:
    def setup_method(self) -> None:
        self.crawler = get_crawler(Spider)
        self.mw = build_from_crawler(DownloaderStats, self.crawler)

        self.crawler.stats.open_spider()

        self.req = Request("http://scrapytest.org")
        self.res = Response("http://scrapytest.org", status=400)

    def teardown_method(self) -> None:
        self.crawler.stats.close_spider()

    def assertStatsEqual(self, key: str, value: object) -> None:
        assert self.crawler.stats.get_value(key) == value, str(
            self.crawler.stats.get_stats()
        )

    def test_process_request(self) -> None:
        self.mw.process_request(self.req)
        self.assertStatsEqual("downloader/request_count", 1)

    def test_process_response(self) -> None:
        self.mw.process_response(self.req, self.res)
        self.assertStatsEqual("downloader/response_count", 1)

    @pytest.mark.parametrize(
        ("headers", "raw_response"),
        [
            ({}, b"HTTP/1.1 200 OK\r\n\r\nbody"),
            ({"A": "1"}, b"HTTP/1.1 200 OK\r\nA: 1\r\n\r\nbody"),
            (
                [("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")],
                b"HTTP/1.1 200 OK\r\nSet-Cookie: a=1\r\nSet-Cookie: b=2\r\n\r\nbody",
            ),
            ({"A": "1", "B": None}, b"HTTP/1.1 200 OK\r\nA: 1\r\n\r\nbody"),
        ],
    )
    def test_response_bytes(
        self,
        headers: dict[str, str | None] | list[tuple[str, str]],
        raw_response: bytes,
    ) -> None:
        res = Response("http://scrapytest.org", headers=headers, body=b"body")
        self.mw.process_response(self.req, res)
        self.assertStatsEqual("downloader/response_bytes", len(raw_response))

    def test_process_exception(self) -> None:
        self.mw.process_exception(self.req, MyException())
        self.assertStatsEqual("downloader/exception_count", 1)
        self.assertStatsEqual(
            "downloader/exception_type_count/tests.test_downloadermiddleware_stats.MyException",
            1,
        )

    def test_from_crawler_not_configured(self) -> None:
        crawler = get_crawler(Spider, {"DOWNLOADER_STATS": False})
        with pytest.raises(NotConfigured):
            build_from_crawler(DownloaderStats, crawler)


def test_get_header_size_non_list_value() -> None:
    # Deliberately passing a non-list/tuple header value to make sure
    # get_header_size() degrades gracefully instead of raising.
    assert get_header_size({"Content-Type": "text/html"}) == 0  # type: ignore[dict-item]
