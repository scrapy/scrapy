import json
import socket
import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import docrawl, get_testlog
from scrapy.tests.spiders import FollowAllSpider, DelaySpider, SimpleSpider, \
    BrokenStartRequestsSpider, SingleRequestSpider, DuplicateStartRequestsSpider
from scrapy.tests.mockserver import MockServer
from scrapy.http import Request


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
        with mock.patch('socket.gethostbyname',
                        side_effect=socket.gaierror(-5, 'No address associated with hostname')):
            spider = SimpleSpider("http://example.com/")
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
    def test_start_requests_dupes(self):
        settings = {"CONCURRENT_REQUESTS": 1}
        spider = DuplicateStartRequestsSpider(dont_filter=True,
                                              distinct_urls=2,
                                              dupe_factor=3)
        yield docrawl(spider, settings)
        self.assertEqual(spider.visited, 6)

        spider = DuplicateStartRequestsSpider(dont_filter=False,
                                              distinct_urls=3,
                                              dupe_factor=4)
        yield docrawl(spider, settings)
        self.assertEqual(spider.visited, 3)

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

    @defer.inlineCallbacks
    def test_referer_header(self):
        """Referer header is set by RefererMiddleware unless it is already set"""
        req0 = Request('http://localhost:8998/echo?headers=1&body=0', dont_filter=1)
        req1 = req0.replace()
        req2 = req0.replace(headers={'Referer': None})
        req3 = req0.replace(headers={'Referer': 'http://example.com'})
        req0.meta['next'] = req1
        req1.meta['next'] = req2
        req2.meta['next'] = req3
        spider = SingleRequestSpider(seed=req0)
        yield docrawl(spider)
        # basic asserts in case of weird communication errors
        self.assertIn('responses', spider.meta)
        self.assertNotIn('failures', spider.meta)
        # start requests doesn't set Referer header
        echo0 = json.loads(spider.meta['responses'][2].body)
        self.assertNotIn('Referer', echo0['headers'])
        # following request sets Referer to start request url
        echo1 = json.loads(spider.meta['responses'][1].body)
        self.assertEqual(echo1['headers'].get('Referer'), [req0.url])
        # next request avoids Referer header
        echo2 = json.loads(spider.meta['responses'][2].body)
        self.assertNotIn('Referer', echo2['headers'])
        # last request explicitly sets a Referer header
        echo3 = json.loads(spider.meta['responses'][3].body)
        self.assertEqual(echo3['headers'].get('Referer'), ['http://example.com'])

    @defer.inlineCallbacks
    def test_engine_status(self):
        from scrapy.utils.engine import get_engine_status
        est = []

        def cb(response):
            est.append(get_engine_status(spider.crawler.engine))

        spider = SingleRequestSpider(seed='http://localhost:8998/', callback_func=cb)
        yield docrawl(spider)
        self.assertEqual(len(est), 1, est)
        s = dict(est[0])
        self.assertEqual(s['engine.spider.name'], spider.name)
        self.assertEqual(s['len(engine.scraper.slot.active)'], 1)
