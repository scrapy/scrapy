from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.exceptions import StopDownload
from tests.test_engine import (
    AttrsItemsSpider,
    CrawlerRun,
    DataClassItemsSpider,
    DictItemsSpider,
    MySpider,
    TestEngineBase,
)
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class HeadersReceivedCrawlerRun(CrawlerRun):
    def headers_received(self, headers, body_length, request, spider):
        super().headers_received(headers, body_length, request, spider)
        raise StopDownload(fail=False)


class TestHeadersReceivedEngine(TestEngineBase):
    @pytest.mark.requires_http_handler
    @coroutine_test
    async def test_crawler(
        self, mockserver: MockServer, caplog: pytest.LogCaptureFixture
    ) -> None:
        for spider in (
            MySpider,
            DictItemsSpider,
            AttrsItemsSpider,
            DataClassItemsSpider,
        ):
            run = HeadersReceivedCrawlerRun(spider)
            with caplog.at_level("DEBUG"):
                await run.run(mockserver)
            for url in ("/redirected", "/static/", "/numbers"):
                assert (
                    f"Download stopped for <GET {mockserver.url(url)}> "
                    "from signal handler HeadersReceivedCrawlerRun.headers_received"
                ) in caplog.text
            self._assert_visited_urls(run)
            self._assert_downloaded_responses(run, count=6)
            self._assert_signals_caught(run)
            self._assert_bytes_received(run)
            self._assert_headers_received(run)

    @staticmethod
    def _assert_bytes_received(run: CrawlerRun) -> None:
        assert len(run.bytes) == 0

    @staticmethod
    def _assert_visited_urls(run: CrawlerRun) -> None:
        must_be_visited = ["/static/", "/redirect", "/redirected"]
        urls_visited = {rp[0].url for rp in run.respplug}
        urls_expected = {run.geturl(p) for p in must_be_visited}
        assert urls_expected <= urls_visited, (
            f"URLs not visited: {list(urls_expected - urls_visited)}"
        )
