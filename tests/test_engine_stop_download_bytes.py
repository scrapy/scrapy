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


class BytesReceivedCrawlerRun(CrawlerRun):
    def bytes_received(self, data, request, spider):
        super().bytes_received(data, request, spider)
        raise StopDownload(fail=False)


class TestBytesReceivedEngine(TestEngineBase):
    @deferred_f_from_coro_f
    async def test_crawler(self, mockserver: MockServer) -> None:
        for spider in (
            MySpider,
            DictItemsSpider,
            AttrsItemsSpider,
            DataClassItemsSpider,
        ):
            run = BytesReceivedCrawlerRun(spider)
            with LogCapture() as log:
                await run.run(mockserver)
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET {mockserver.url('/redirected')}> "
                        "from signal handler BytesReceivedCrawlerRun.bytes_received",
                    )
                )
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET {mockserver.url('/static/')}> "
                        "from signal handler BytesReceivedCrawlerRun.bytes_received",
                    )
                )
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET {mockserver.url('/numbers')}> "
                        "from signal handler BytesReceivedCrawlerRun.bytes_received",
                    )
                )
            self._assert_visited_urls(run)
            self._assert_scheduled_requests(run, count=9)
            self._assert_downloaded_responses(run, count=9)
            self._assert_signals_caught(run)
            self._assert_headers_received(run)
            self._assert_bytes_received(run)

    @staticmethod
    def _assert_bytes_received(run: CrawlerRun) -> None:
        assert len(run.bytes) == 9
        for request, data in run.bytes.items():
            joined_data = b"".join(data)
            assert len(data) == 1  # signal was fired only once
            if run.getpath(request.url) == "/numbers":
                # Received bytes are not the complete response. The exact amount depends
                # on the buffer size, which can vary, so we only check that the amount
                # of received bytes is strictly less than the full response.
                numbers = [str(x).encode("utf8") for x in range(2**18)]
                assert len(joined_data) < len(b"".join(numbers))
