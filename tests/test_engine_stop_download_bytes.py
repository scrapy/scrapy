from testfixtures import LogCapture
from twisted.internet import defer

from scrapy.exceptions import StopDownload

from tests.test_engine import (
    AttrsItemsSpider,
    DataClassItemsSpider,
    DictItemsSpider,
    TestSpider,
    CrawlerRun,
    EngineTest,
)


class BytesReceivedCrawlerRun(CrawlerRun):
    def bytes_received(self, data, request, spider):
        super().bytes_received(data, request, spider)
        raise StopDownload(fail=False)


class BytesReceivedEngineTest(EngineTest):
    @defer.inlineCallbacks
    def test_crawler(self):
        for spider in (TestSpider, DictItemsSpider, AttrsItemsSpider, DataClassItemsSpider):
            if spider is None:
                continue
            self.run = BytesReceivedCrawlerRun(spider)
            with LogCapture() as log:
                yield self.run.run()
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   f"Download stopped for <GET http://localhost:{self.run.portno}/redirected> "
                                   "from signal handler BytesReceivedCrawlerRun.bytes_received"))
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   f"Download stopped for <GET http://localhost:{self.run.portno}/> "
                                   "from signal handler BytesReceivedCrawlerRun.bytes_received"))
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   f"Download stopped for <GET http://localhost:{self.run.portno}/numbers> "
                                   "from signal handler BytesReceivedCrawlerRun.bytes_received"))
            self._assert_visited_urls()
            self._assert_scheduled_requests(count=9)
            self._assert_downloaded_responses(count=9)
            self._assert_signals_caught()
            self._assert_headers_received()
            self._assert_bytes_received()

    def _assert_bytes_received(self):
        self.assertEqual(9, len(self.run.bytes))
        for request, data in self.run.bytes.items():
            joined_data = b"".join(data)
            self.assertTrue(len(data) == 1)  # signal was fired only once
            if self.run.getpath(request.url) == "/numbers":
                # Received bytes are not the complete response. The exact amount depends
                # on the buffer size, which can vary, so we only check that the amount
                # of received bytes is strictly less than the full response.
                numbers = [str(x).encode("utf8") for x in range(2**18)]
                self.assertTrue(len(joined_data) < len(b"".join(numbers)))
