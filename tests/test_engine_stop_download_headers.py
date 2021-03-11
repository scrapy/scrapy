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


class HeadersReceivedCrawlerRun(CrawlerRun):
    def headers_received(self, headers, body_length, request, spider):
        super().headers_received(headers, body_length, request, spider)
        raise StopDownload(fail=False)


class HeadersReceivedEngineTest(EngineTest):
    @defer.inlineCallbacks
    def test_crawler(self):
        for spider in (TestSpider, DictItemsSpider, AttrsItemsSpider, DataClassItemsSpider):
            if spider is None:
                continue
            self.run = HeadersReceivedCrawlerRun(spider)
            with LogCapture() as log:
                yield self.run.run()
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   f"Download stopped for <GET http://localhost:{self.run.portno}/redirected> from"
                                   " signal handler HeadersReceivedCrawlerRun.headers_received"))
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   f"Download stopped for <GET http://localhost:{self.run.portno}/> from signal"
                                   " handler HeadersReceivedCrawlerRun.headers_received"))
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   f"Download stopped for <GET http://localhost:{self.run.portno}/numbers> from"
                                   " signal handler HeadersReceivedCrawlerRun.headers_received"))
            self._assert_visited_urls()
            self._assert_downloaded_responses(count=6)
            self._assert_signals_caught()
            self._assert_bytes_received()
            self._assert_headers_received()

    def _assert_bytes_received(self):
        self.assertEqual(0, len(self.run.bytes))

    def _assert_visited_urls(self):
        must_be_visited = ["/", "/redirect", "/redirected"]
        urls_visited = {rp[0].url for rp in self.run.respplug}
        urls_expected = {self.run.geturl(p) for p in must_be_visited}
        assert urls_expected <= urls_visited, f"URLs not visited: {list(urls_expected - urls_visited)}"
