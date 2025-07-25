from __future__ import annotations

from typing import TYPE_CHECKING

from testfixtures import LogCapture

from scrapy.exceptions import StopDownload
from scrapy.utils.defer import deferred_f_from_coro_f
from tests.test_engine import (
    AttrsItemsSpider,
    CrawlerRun,
    DataClassItemsSpider,
    DictItemsSpider,
    MySpider,
    TestEngineBase,
)

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class HeadersReceivedCrawlerRun(CrawlerRun):
    def headers_received(self, headers, body_length, request, spider):
        super().headers_received(headers, body_length, request, spider)
        raise StopDownload(fail=False)


class TestHeadersReceivedEngine(TestEngineBase):
    @deferred_f_from_coro_f
    async def test_crawler(self, mockserver: MockServer) -> None:
        for spider in (
            MySpider,
            DictItemsSpider,
            AttrsItemsSpider,
            DataClassItemsSpider,
        ):
            run = HeadersReceivedCrawlerRun(spider)
            with LogCapture() as log:
                await run.run(mockserver)
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET {mockserver.url('/redirected')}> from"
                        " signal handler HeadersReceivedCrawlerRun.headers_received",
                    )
                )
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET {mockserver.url('/static/')}> from signal"
                        " handler HeadersReceivedCrawlerRun.headers_received",
                    )
                )
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET {mockserver.url('/numbers')}> from"
                        " signal handler HeadersReceivedCrawlerRun.headers_received",
                    )
                )
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
