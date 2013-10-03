from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import get_crawler, get_testlog
from scrapy.tests.spiders import FollowAllSpider, DelaySpider, SimpleSpider, \
    BrokenStartRequestsSpider
from scrapy.tests.mockserver import MockServer


def docrawl(spider, settings=None):
    crawler = get_crawler(settings)
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

    @defer.inlineCallbacks
    def test_start_requests_bug_before_yield(self):
        spider = BrokenStartRequestsSpider(fail_before_yield=1)
        yield docrawl(spider)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEqual(len(errors), 1)

    @defer.inlineCallbacks
    def test_start_requests_bug_yielding(self):
        spider = BrokenStartRequestsSpider(fail_yielding=1)
        yield docrawl(spider)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEqual(len(errors), 1)

    @defer.inlineCallbacks
    def test_start_requests_lazyness(self):
        settings = {"CONCURRENT_REQUESTS": 1}
        spider = BrokenStartRequestsSpider()
        yield docrawl(spider, settings)
        #self.assertTrue(False, spider.seedsseen)
        #self.assertTrue(spider.seedsseen.index(None) < spider.seedsseen.index(99),
        #                spider.seedsseen)

    @defer.inlineCallbacks
    def test_unbounded_response(self):
        # Completeness of responses without Content-Length or Transfer-Encoding
        # can not be determined, we treat them as valid but flagged as "partial"
        from urllib import urlencode
        query = urlencode({'raw': '''\
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1
X-Powered-By: Servlet 2.4; JBoss-4.2.3.GA (build: SVNTag=JBoss_4_2_3_GA date=200807181417)/JBossWeb-2.0
Set-Cookie: JSESSIONID=08515F572832D0E659FD2B0D8031D75F; Path=/
Pragma: no-cache
Expires: Thu, 01 Jan 1970 00:00:00 GMT
Cache-Control: no-cache
Cache-Control: no-store
Content-Type: text/html;charset=UTF-8
Content-Language: en
Date: Tue, 27 Aug 2013 13:05:05 GMT
Connection: close

foo body
with multiples lines
'''})
        spider = SimpleSpider("http://localhost:8998/raw?{0}".format(query))
        yield docrawl(spider)
        log = get_testlog()
        self.assertEqual(log.count("Got response 200"), 1)

    @defer.inlineCallbacks
    def test_retry_conn_lost(self):
        # connection lost after receiving data
        spider = SimpleSpider("http://localhost:8998/drop?abort=0")
        yield docrawl(spider)
        self._assert_retried()

    @defer.inlineCallbacks
    def test_retry_conn_aborted(self):
        # connection lost before receiving data
        spider = SimpleSpider("http://localhost:8998/drop?abort=1")
        yield docrawl(spider)
        self._assert_retried()

    def _assert_retried(self):
        log = get_testlog()
        self.assertEqual(log.count("Retrying"), 2)
        self.assertEqual(log.count("Gave up retrying"), 1)
