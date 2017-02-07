import unittest
from twisted.internet import defer
from twisted.internet.error import TimeoutError, DNSLookupError, \
        ConnectionRefusedError, ConnectionDone, ConnectError, \
        ConnectionLost, TCPTimedOutError
from twisted.web.client import ResponseFailed

from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.utils.test import get_crawler


class RetryTest(unittest.TestCase):
    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider('foo')
        self.mw = RetryMiddleware.from_crawler(self.crawler)
        self.mw.max_retry_times = 2

    def test_priority_adjust(self):
        req = Request('http://www.scrapytest.org/503')
        rsp = Response('http://www.scrapytest.org/503', body=b'', status=503)
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert req2.priority < req.priority

    def test_404(self):
        req = Request('http://www.scrapytest.org/404')
        rsp = Response('http://www.scrapytest.org/404', body=b'', status=404)

        # dont retry 404s
        assert self.mw.process_response(req, rsp, self.spider) is rsp

    def test_dont_retry(self):
        req = Request('http://www.scrapytest.org/503', meta={'dont_retry': True})
        rsp = Response('http://www.scrapytest.org/503', body=b'', status=503)

        # first retry
        r = self.mw.process_response(req, rsp, self.spider)
        assert r is rsp

        # Test retry when dont_retry set to False
        req = Request('http://www.scrapytest.org/503', meta={'dont_retry': False})
        rsp = Response('http://www.scrapytest.org/503')

        # first retry
        r = self.mw.process_response(req, rsp, self.spider)
        assert r is rsp

    def test_dont_retry_exc(self):
        req = Request('http://www.scrapytest.org/503', meta={'dont_retry': True})

        r = self.mw.process_exception(req, DNSLookupError(), self.spider)
        assert r is None

    def test_503(self):
        req = Request('http://www.scrapytest.org/503')
        rsp = Response('http://www.scrapytest.org/503', body=b'', status=503)

        # first retry
        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        self.assertEqual(req.meta['retry_times'], 1)

        # second retry
        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        self.assertEqual(req.meta['retry_times'], 2)

        # discard it
        assert self.mw.process_response(req, rsp, self.spider) is rsp

        assert self.crawler.stats.get_value('retry/max_reached') == 1
        assert self.crawler.stats.get_value('retry/reason_count/503 Service Unavailable') == 2
        assert self.crawler.stats.get_value('retry/count') == 2

    def test_twistederrors(self):
        exceptions = [defer.TimeoutError, TCPTimedOutError, TimeoutError,
                DNSLookupError, ConnectionRefusedError, ConnectionDone,
                ConnectError, ConnectionLost, ResponseFailed]

        for exc in exceptions:
            req = Request('http://www.scrapytest.org/%s' % exc.__name__)
            self._test_retry_exception(req, exc('foo'))

        stats = self.crawler.stats
        assert stats.get_value('retry/max_reached') == len(exceptions)
        assert stats.get_value('retry/count') == len(exceptions) * 2
        assert stats.get_value('retry/reason_count/twisted.internet.defer.TimeoutError') == 2

    def _test_retry_exception(self, req, exception):
        # first retry
        req = self.mw.process_exception(req, exception, self.spider)
        assert isinstance(req, Request)
        self.assertEqual(req.meta['retry_times'], 1)

        # second retry
        req = self.mw.process_exception(req, exception, self.spider)
        assert isinstance(req, Request)
        self.assertEqual(req.meta['retry_times'], 2)

        # discard it
        req = self.mw.process_exception(req, exception, self.spider)
        self.assertEqual(req, None)


if __name__ == "__main__":
    unittest.main()
