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


class BytesReceivedCrawlerRun(CrawlerRun):
    def bytes_received(self, data, request, spider):
        super().bytes_received(data, request, spider)
        raise StopDownload(fail=False)


class TestBytesReceivedEngine(TestEngineBase):
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
            run = BytesReceivedCrawlerRun(spider)
            with caplog.at_level("DEBUG"):
                await run.run(mockserver)
            for url in ("/redirected", "/static/", "/numbers"):
                assert (
                    f"Download stopped for <GET {mockserver.url(url)}> "
                    "from signal handler BytesReceivedCrawlerRun.bytes_received"
                ) in caplog.text
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
