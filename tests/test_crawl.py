import json
import logging

from pytest import mark
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy import signals
from scrapy.crawler import CrawlerRunner
from scrapy.http import Request
from scrapy.utils.python import to_unicode
from tests.mockserver import MockServer
from tests.spiders import (FollowAllSpider, DelaySpider, SimpleSpider, BrokenStartRequestsSpider,
                           SingleRequestSpider, DuplicateStartRequestsSpider, CrawlSpiderWithErrback,
                           AsyncDefSpider, AsyncDefAsyncioSpider, AsyncDefAsyncioReturnSpider)


class CrawlTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self.runner = CrawlerRunner()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_follow_all(self):
        crawler = self.runner.create_crawler(FollowAllSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(len(crawler.spider.urls_visited), 11)  # 10 + start_url

    @defer.inlineCallbacks
    def test_fixed_delay(self):
        yield self._test_delay(total=3, delay=0.1)

    @defer.inlineCallbacks
    def test_randomized_delay(self):
        yield self._test_delay(total=3, delay=0.1, randomize=True)

    @defer.inlineCallbacks
    def _test_delay(self, total, delay, randomize=False):
        crawl_kwargs = dict(
            maxlatency=delay * 2,
            mockserver=self.mockserver,
            total=total,
        )
        tolerance = (1 - (0.6 if randomize else 0.2))

        settings = {"DOWNLOAD_DELAY": delay,
                    'RANDOMIZE_DOWNLOAD_DELAY': randomize}
        crawler = CrawlerRunner(settings).create_crawler(FollowAllSpider)
        yield crawler.crawl(**crawl_kwargs)
        times = crawler.spider.times
        total_time = times[-1] - times[0]
        average = total_time / (len(times) - 1)
        self.assertTrue(average > delay * tolerance,
                        "download delay too small: %s" % average)

        # Ensure that the same test parameters would cause a failure if no
        # download delay is set. Otherwise, it means we are using a combination
        # of ``total`` and ``delay`` values that are too small for the test
        # code above to have any meaning.
        settings["DOWNLOAD_DELAY"] = 0
        crawler = CrawlerRunner(settings).create_crawler(FollowAllSpider)
        yield crawler.crawl(**crawl_kwargs)
        times = crawler.spider.times
        total_time = times[-1] - times[0]
        average = total_time / (len(times) - 1)
        self.assertFalse(average > delay / tolerance,
                         "test total or delay values are too small")

    @defer.inlineCallbacks
    def test_timeout_success(self):
        crawler = self.runner.create_crawler(DelaySpider)
        yield crawler.crawl(n=0.5, mockserver=self.mockserver)
        self.assertTrue(crawler.spider.t1 > 0)
        self.assertTrue(crawler.spider.t2 > 0)
        self.assertTrue(crawler.spider.t2 > crawler.spider.t1)

    @defer.inlineCallbacks
    def test_timeout_failure(self):
        crawler = CrawlerRunner({"DOWNLOAD_TIMEOUT": 0.35}).create_crawler(DelaySpider)
        yield crawler.crawl(n=0.5, mockserver=self.mockserver)
        self.assertTrue(crawler.spider.t1 > 0)
        self.assertTrue(crawler.spider.t2 == 0)
        self.assertTrue(crawler.spider.t2_err > 0)
        self.assertTrue(crawler.spider.t2_err > crawler.spider.t1)
        # server hangs after receiving response headers
        yield crawler.crawl(n=0.5, b=1, mockserver=self.mockserver)
        self.assertTrue(crawler.spider.t1 > 0)
        self.assertTrue(crawler.spider.t2 == 0)
        self.assertTrue(crawler.spider.t2_err > 0)
        self.assertTrue(crawler.spider.t2_err > crawler.spider.t1)

    @defer.inlineCallbacks
    def test_retry_503(self):
        crawler = self.runner.create_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/status?n=503"), mockserver=self.mockserver)
        self._assert_retried(l)

    @defer.inlineCallbacks
    def test_retry_conn_failed(self):
        crawler = self.runner.create_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl("http://localhost:65432/status?n=503", mockserver=self.mockserver)
        self._assert_retried(l)

    @defer.inlineCallbacks
    def test_retry_dns_error(self):
        crawler = self.runner.create_crawler(SimpleSpider)
        with LogCapture() as l:
            # try to fetch the homepage of a non-existent domain
            yield crawler.crawl("http://dns.resolution.invalid./", mockserver=self.mockserver)
        self._assert_retried(l)

    @defer.inlineCallbacks
    def test_start_requests_bug_before_yield(self):
        with LogCapture('scrapy', level=logging.ERROR) as l:
            crawler = self.runner.create_crawler(BrokenStartRequestsSpider)
            yield crawler.crawl(fail_before_yield=1, mockserver=self.mockserver)

        self.assertEqual(len(l.records), 1)
        record = l.records[0]
        self.assertIsNotNone(record.exc_info)
        self.assertIs(record.exc_info[0], ZeroDivisionError)

    @defer.inlineCallbacks
    def test_start_requests_bug_yielding(self):
        with LogCapture('scrapy', level=logging.ERROR) as l:
            crawler = self.runner.create_crawler(BrokenStartRequestsSpider)
            yield crawler.crawl(fail_yielding=1, mockserver=self.mockserver)

        self.assertEqual(len(l.records), 1)
        record = l.records[0]
        self.assertIsNotNone(record.exc_info)
        self.assertIs(record.exc_info[0], ZeroDivisionError)

    @defer.inlineCallbacks
    def test_start_requests_lazyness(self):
        settings = {"CONCURRENT_REQUESTS": 1}
        crawler = CrawlerRunner(settings).create_crawler(BrokenStartRequestsSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        #self.assertTrue(False, crawler.spider.seedsseen)
        #self.assertTrue(crawler.spider.seedsseen.index(None) < crawler.spider.seedsseen.index(99),
        #                crawler.spider.seedsseen)

    @defer.inlineCallbacks
    def test_start_requests_dupes(self):
        settings = {"CONCURRENT_REQUESTS": 1}
        crawler = CrawlerRunner(settings).create_crawler(DuplicateStartRequestsSpider)
        yield crawler.crawl(dont_filter=True, distinct_urls=2, dupe_factor=3, mockserver=self.mockserver)
        self.assertEqual(crawler.spider.visited, 6)

        yield crawler.crawl(dont_filter=False, distinct_urls=3, dupe_factor=4, mockserver=self.mockserver)
        self.assertEqual(crawler.spider.visited, 3)

    @defer.inlineCallbacks
    def test_unbounded_response(self):
        # Completeness of responses without Content-Length or Transfer-Encoding
        # can not be determined, we treat them as valid but flagged as "partial"
        from urllib.parse import urlencode
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
        crawler = self.runner.create_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/raw?{0}".format(query)), mockserver=self.mockserver)
        self.assertEqual(str(l).count("Got response 200"), 1)

    @defer.inlineCallbacks
    def test_retry_conn_lost(self):
        # connection lost after receiving data
        crawler = self.runner.create_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/drop?abort=0"), mockserver=self.mockserver)
        self._assert_retried(l)

    @defer.inlineCallbacks
    def test_retry_conn_aborted(self):
        # connection lost before receiving data
        crawler = self.runner.create_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/drop?abort=1"), mockserver=self.mockserver)
        self._assert_retried(l)

    def _assert_retried(self, log):
        self.assertEqual(str(log).count("Retrying"), 2)
        self.assertEqual(str(log).count("Gave up retrying"), 1)

    @defer.inlineCallbacks
    def test_referer_header(self):
        """Referer header is set by RefererMiddleware unless it is already set"""
        req0 = Request(self.mockserver.url('/echo?headers=1&body=0'), dont_filter=1)
        req1 = req0.replace()
        req2 = req0.replace(headers={'Referer': None})
        req3 = req0.replace(headers={'Referer': 'http://example.com'})
        req0.meta['next'] = req1
        req1.meta['next'] = req2
        req2.meta['next'] = req3
        crawler = self.runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=req0, mockserver=self.mockserver)
        # basic asserts in case of weird communication errors
        self.assertIn('responses', crawler.spider.meta)
        self.assertNotIn('failures', crawler.spider.meta)
        # start requests doesn't set Referer header
        echo0 = json.loads(to_unicode(crawler.spider.meta['responses'][2].body))
        self.assertNotIn('Referer', echo0['headers'])
        # following request sets Referer to start request url
        echo1 = json.loads(to_unicode(crawler.spider.meta['responses'][1].body))
        self.assertEqual(echo1['headers'].get('Referer'), [req0.url])
        # next request avoids Referer header
        echo2 = json.loads(to_unicode(crawler.spider.meta['responses'][2].body))
        self.assertNotIn('Referer', echo2['headers'])
        # last request explicitly sets a Referer header
        echo3 = json.loads(to_unicode(crawler.spider.meta['responses'][3].body))
        self.assertEqual(echo3['headers'].get('Referer'), ['http://example.com'])

    @defer.inlineCallbacks
    def test_engine_status(self):
        from scrapy.utils.engine import get_engine_status
        est = []

        def cb(response):
            est.append(get_engine_status(crawler.engine))

        crawler = self.runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=self.mockserver.url('/'), callback_func=cb, mockserver=self.mockserver)
        self.assertEqual(len(est), 1, est)
        s = dict(est[0])
        self.assertEqual(s['engine.spider.name'], crawler.spider.name)
        self.assertEqual(s['len(engine.scraper.slot.active)'], 1)

    @defer.inlineCallbacks
    def test_graceful_crawl_error_handling(self):
        """
        Test whether errors happening anywhere in Crawler.crawl() are properly
        reported (and not somehow swallowed) after a graceful engine shutdown.
        The errors should not come from within Scrapy's core but from within
        spiders/middlewares/etc., e.g. raised in Spider.start_requests(),
        SpiderMiddleware.process_start_requests(), etc.
        """

        class TestError(Exception):
            pass

        class FaultySpider(SimpleSpider):
            def start_requests(self):
                raise TestError

        crawler = self.runner.create_crawler(FaultySpider)
        yield self.assertFailure(crawler.crawl(mockserver=self.mockserver), TestError)
        self.assertFalse(crawler.crawling)

    @defer.inlineCallbacks
    def test_open_spider_error_on_faulty_pipeline(self):
        settings = {
            "ITEM_PIPELINES": {
                "tests.pipelines.ZeroDivisionErrorPipeline": 300,
            }
        }
        crawler = CrawlerRunner(settings).create_crawler(SimpleSpider)
        yield self.assertFailure(
            self.runner.crawl(crawler, self.mockserver.url("/status?n=200"), mockserver=self.mockserver),
            ZeroDivisionError)
        self.assertFalse(crawler.crawling)

    @defer.inlineCallbacks
    def test_crawlerrunner_accepts_crawler(self):
        crawler = self.runner.create_crawler(SimpleSpider)
        with LogCapture() as log:
            yield self.runner.crawl(crawler, self.mockserver.url("/status?n=200"), mockserver=self.mockserver)
        self.assertIn("Got response 200", str(log))

    @defer.inlineCallbacks
    def test_crawl_multiple(self):
        self.runner.crawl(SimpleSpider, self.mockserver.url("/status?n=200"), mockserver=self.mockserver)
        self.runner.crawl(SimpleSpider, self.mockserver.url("/status?n=503"), mockserver=self.mockserver)

        with LogCapture() as log:
            yield self.runner.join()

        self._assert_retried(log)
        self.assertIn("Got response 200", str(log))

    @defer.inlineCallbacks
    def test_crawlspider_with_errback(self):
        self.runner.crawl(CrawlSpiderWithErrback, mockserver=self.mockserver)

        with LogCapture() as log:
            yield self.runner.join()

        self.assertIn("[callback] status 200", str(log))
        self.assertIn("[callback] status 201", str(log))
        self.assertIn("[errback] status 404", str(log))
        self.assertIn("[errback] status 500", str(log))

    @defer.inlineCallbacks
    def test_async_def_parse(self):
        self.runner.crawl(AsyncDefSpider, self.mockserver.url("/status?n=200"), mockserver=self.mockserver)
        with LogCapture() as log:
            yield self.runner.join()
        self.assertIn("Got response 200", str(log))

    @mark.only_asyncio()
    @defer.inlineCallbacks
    def test_async_def_asyncio_parse(self):
        runner = CrawlerRunner({"ASYNCIO_REACTOR": True})
        runner.crawl(AsyncDefAsyncioSpider, self.mockserver.url("/status?n=200"), mockserver=self.mockserver)
        with LogCapture() as log:
            yield runner.join()
        self.assertIn("Got response 200", str(log))

    @mark.only_asyncio()
    @defer.inlineCallbacks
    def test_async_def_asyncio_parse_list(self):
        items = []

        def _on_item_scraped(item):
            items.append(item)

        crawler = self.runner.create_crawler(AsyncDefAsyncioReturnSpider)
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        with LogCapture() as log:
            yield crawler.crawl(self.mockserver.url("/status?n=200"), mockserver=self.mockserver)
        self.assertIn("Got response 200", str(log))
        self.assertIn({'id': 1}, items)
        self.assertIn({'id': 2}, items)
