from testfixtures import LogCapture
from twisted.internet import defer

from scrapy.exceptions import StopDownload
from tests.test_engine import (
    AttrsItemsSpider,
    CrawlerRun,
    DataClassItemsSpider,
    DictItemsSpider,
    MySpider,
    TestEngineBase,
)


class BytesReceivedCrawlerRun(CrawlerRun):
    def bytes_received(self, data, request, spider):
        super().bytes_received(data, request, spider)
        raise StopDownload(fail=False)


class TestBytesReceivedEngine(TestEngineBase):
    @defer.inlineCallbacks
    def test_crawler(self):
        for spider in (
            MySpider,
            DictItemsSpider,
            AttrsItemsSpider,
            DataClassItemsSpider,
        ):
            run = BytesReceivedCrawlerRun(spider)
            with LogCapture() as log:
                yield run.run()
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET http://localhost:{run.portno}/redirected> "
                        "from signal handler BytesReceivedCrawlerRun.bytes_received",
                    )
                )
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET http://localhost:{run.portno}/> "
                        "from signal handler BytesReceivedCrawlerRun.bytes_received",
                    )
                )
                log.check_present(
                    (
                        "scrapy.core.downloader.handlers.http11",
                        "DEBUG",
                        f"Download stopped for <GET http://localhost:{run.portno}/numbers> "
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
