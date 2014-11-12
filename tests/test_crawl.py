import json
import socket
import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import get_crawler, get_testlog
from tests.spiders import FollowAllSpider, DelaySpider, SimpleSpider, \
    BrokenStartRequestsSpider, SingleRequestSpider, DuplicateStartRequestsSpider
from tests.mockserver import MockServer
from scrapy.http import Request


class CrawlTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_follow_all(self):
        crawler = get_crawler(FollowAllSpider)
        yield crawler.crawl()
        self.assertEqual(len(crawler.spider.urls_visited), 11)  # 10 + start_url

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
        crawler = get_crawler(FollowAllSpider, settings)
        yield crawler.crawl(maxlatency=delay * 2)
        t = crawler.spider.times
        totaltime = t[-1] - t[0]
        avgd = totaltime / (len(t) - 1)
        tolerance = 0.6 if randomize else 0.2
        self.assertTrue(avgd > delay * (1 - tolerance),
                        "download delay too small: %s" % avgd)

    @defer.inlineCallbacks
    def test_timeout_success(self):
        crawler = get_crawler(DelaySpider)
        yield crawler.crawl(n=0.5)
        self.assertTrue(crawler.spider.t1 > 0)
        self.assertTrue(crawler.spider.t2 > 0)
        self.assertTrue(crawler.spider.t2 > crawler.spider.t1)

    @defer.inlineCallbacks
    def test_timeout_failure(self):
        crawler = get_crawler(DelaySpider, {"DOWNLOAD_TIMEOUT": 0.35})
        yield crawler.crawl(n=0.5)
        self.assertTrue(crawler.spider.t1 > 0)
        self.assertTrue(crawler.spider.t2 == 0)
        self.assertTrue(crawler.spider.t2_err > 0)
        self.assertTrue(crawler.spider.t2_err > crawler.spider.t1)
        # server hangs after receiving response headers
        yield crawler.crawl(n=0.5, b=1)
        self.assertTrue(crawler.spider.t1 > 0)
        self.assertTrue(crawler.spider.t2 == 0)
        self.assertTrue(crawler.spider.t2_err > 0)
        self.assertTrue(crawler.spider.t2_err > crawler.spider.t1)

    @defer.inlineCallbacks
    def test_retry_503(self):
        crawler = get_crawler(SimpleSpider)
        yield crawler.crawl("http://localhost:8998/status?n=503")
        self._assert_retried()

    @defer.inlineCallbacks
    def test_retry_conn_failed(self):
        crawler = get_crawler(SimpleSpider)
        yield crawler.crawl("http://localhost:65432/status?n=503")
        self._assert_retried()

    @defer.inlineCallbacks
    def test_retry_dns_error(self):
        with mock.patch('socket.gethostbyname',
                        side_effect=socket.gaierror(-5, 'No address associated with hostname')):
            crawler = get_crawler(SimpleSpider)
            yield crawler.crawl("http://example.com/")
            self._assert_retried()

    @defer.inlineCallbacks
    def test_start_requests_bug_before_yield(self):
        crawler = get_crawler(BrokenStartRequestsSpider)
        yield crawler.crawl(fail_before_yield=1)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEqual(len(errors), 1)

    @defer.inlineCallbacks
    def test_start_requests_bug_yielding(self):
        crawler = get_crawler(BrokenStartRequestsSpider)
        yield crawler.crawl(fail_yielding=1)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEqual(len(errors), 1)

    @defer.inlineCallbacks
    def test_start_requests_lazyness(self):
        settings = {"CONCURRENT_REQUESTS": 1}
        crawler = get_crawler(BrokenStartRequestsSpider, settings)
        yield crawler.crawl()
        #self.assertTrue(False, crawler.spider.seedsseen)
        #self.assertTrue(crawler.spider.seedsseen.index(None) < crawler.spider.seedsseen.index(99),
        #                crawler.spider.seedsseen)

    @defer.inlineCallbacks
    def test_start_requests_dupes(self):
        settings = {"CONCURRENT_REQUESTS": 1}
        crawler = get_crawler(DuplicateStartRequestsSpider, settings)
        yield crawler.crawl(dont_filter=True, distinct_urls=2, dupe_factor=3)
        self.assertEqual(crawler.spider.visited, 6)

        yield crawler.crawl(dont_filter=False, distinct_urls=3, dupe_factor=4)
        self.assertEqual(crawler.spider.visited, 3)

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
        crawler = get_crawler(SimpleSpider)
        yield crawler.crawl("http://localhost:8998/raw?{0}".format(query))
        log = get_testlog()
        self.assertEqual(log.count("Got response 200"), 1)

    @defer.inlineCallbacks
    def test_retry_conn_lost(self):
        # connection lost after receiving data
        crawler = get_crawler(SimpleSpider)
        yield crawler.crawl("http://localhost:8998/drop?abort=0")
        self._assert_retried()

    @defer.inlineCallbacks
    def test_retry_conn_aborted(self):
        # connection lost before receiving data
        crawler = get_crawler(SimpleSpider)
        yield crawler.crawl("http://localhost:8998/drop?abort=1")
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
        crawler = get_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=req0)
        # basic asserts in case of weird communication errors
        self.assertIn('responses', crawler.spider.meta)
        self.assertNotIn('failures', crawler.spider.meta)
        # start requests doesn't set Referer header
        echo0 = json.loads(crawler.spider.meta['responses'][2].body)
        self.assertNotIn('Referer', echo0['headers'])
        # following request sets Referer to start request url
        echo1 = json.loads(crawler.spider.meta['responses'][1].body)
        self.assertEqual(echo1['headers'].get('Referer'), [req0.url])
        # next request avoids Referer header
        echo2 = json.loads(crawler.spider.meta['responses'][2].body)
        self.assertNotIn('Referer', echo2['headers'])
        # last request explicitly sets a Referer header
        echo3 = json.loads(crawler.spider.meta['responses'][3].body)
        self.assertEqual(echo3['headers'].get('Referer'), ['http://example.com'])

    @defer.inlineCallbacks
    def test_engine_status(self):
        from scrapy.utils.engine import get_engine_status
        est = []

        def cb(response):
            est.append(get_engine_status(crawler.engine))

        crawler = get_crawler(SingleRequestSpider)
        yield crawler.crawl(seed='http://localhost:8998/', callback_func=cb)
        self.assertEqual(len(est), 1, est)
        s = dict(est[0])
        self.assertEqual(s['engine.spider.name'], crawler.spider.name)
        self.assertEqual(s['len(engine.scraper.slot.active)'], 1)
