from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import get_crawler, get_testlog
from scrapy.tests.spiders import FollowAllSpider, DelaySpider, SimpleSpider
from scrapy.tests.mockserver import MockServer


def docrawl(spider, settings=None):
    crawler = get_crawler(settings)
    crawler.configure()
    crawler.crawl(spider)
    return crawler.start()


class CrawlTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_follow_all(self):
        spider = FollowAllSpider()
        yield docrawl(spider)
        self.assertEqual(len(spider.urls_visited), 11)  # 10 + start_url

    @defer.inlineCallbacks
    def test_delay(self):
        # short to long delays
        yield self._test_delay(0.2, False)
        yield self._test_delay(1, False)
        # randoms
        yield self._test_delay(0.2, True)
        yield self._test_delay(1, True)

    @defer.inlineCallbacks
    def _test_delay(self, delay, randomize):
        settings = {"DOWNLOAD_DELAY": delay, 'RANDOMIZE_DOWNLOAD_DELAY': randomize}
        spider = FollowAllSpider(maxlatency=delay * 2)
        yield docrawl(spider, settings)
        t = spider.times
        totaltime = t[-1] - t[0]
        avgd = totaltime / (len(t) - 1)
        tolerance = 0.6 if randomize else 0.2
        self.assertTrue(avgd > delay * (1 - tolerance),
                        "download delay too small: %s" % avgd)

    @defer.inlineCallbacks
    def test_timeout_success(self):
        spider = DelaySpider(n=0.5)
        yield docrawl(spider)
        self.assertTrue(spider.t1 > 0)
        self.assertTrue(spider.t2 > 0)
        self.assertTrue(spider.t2 > spider.t1)

    @defer.inlineCallbacks
    def test_timeout_failure(self):
        spider = DelaySpider(n=0.5)
        yield docrawl(spider, {"DOWNLOAD_TIMEOUT": 0.35})
        self.assertTrue(spider.t1 > 0)
        self.assertTrue(spider.t2 == 0)
        self.assertTrue(spider.t2_err > 0)
        self.assertTrue(spider.t2_err > spider.t1)
        # server hangs after receiving response headers
        spider = DelaySpider(n=0.5, b=1)
        yield docrawl(spider, {"DOWNLOAD_TIMEOUT": 0.35})
        self.assertTrue(spider.t1 > 0)
        self.assertTrue(spider.t2 == 0)
        self.assertTrue(spider.t2_err > 0)
        self.assertTrue(spider.t2_err > spider.t1)

    @defer.inlineCallbacks
    def test_retry_503(self):
        spider = SimpleSpider("http://localhost:8998/status?n=503")
        yield docrawl(spider)
        self._assert_retried()

    @defer.inlineCallbacks
    def test_retry_conn_failed(self):
        spider = SimpleSpider("http://localhost:65432/status?n=503")
        yield docrawl(spider)
        self._assert_retried()

    @defer.inlineCallbacks
    def test_retry_dns_error(self):
        spider = SimpleSpider("http://localhost666/status?n=503")
        yield docrawl(spider)
        self._assert_retried()

    def _assert_retried(self):
        log = get_testlog()
        self.assertEqual(log.count("Retrying"), 2)
        self.assertEqual(log.count("Gave up retrying"), 1)
