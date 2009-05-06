import unittest

from twisted.internet.error import TimeoutError as ServerTimeoutError, DNSLookupError, \
                                   ConnectionRefusedError, ConnectionDone, ConnectError, \
                                   ConnectionLost

from scrapy.contrib.downloadermiddleware.retry import RetryMiddleware
from scrapy.core.exceptions import HttpException
from scrapy.spider import spiders
from scrapy.http import Request, Response

class RetryTest(unittest.TestCase):
    def setUp(self):
        spiders.spider_modules = ['scrapy.tests.test_spiders']
        spiders.reload()
        self.spider = spiders.fromdomain('scrapytest.org')
        self.mw = RetryMiddleware()
        self.mw.max_retry_times = 2

    def test_process_exception_404(self):
        req404 = Request('http://www.scrapytest.org/404')
        exc404 = HttpException('404', None, Response('http://www.scrapytest.org/404', body=''))

        # dont retry 404s
        req = self.mw.process_exception(req404, exc404, self.spider)
        self.assertTrue(req is None)

    def test_process_exception_503(self):
        req503 = Request('http://www.scrapytest.org/503')
        exc503 = HttpException('503', None, Response('http://www.scrapytest.org/503', body=''))
        self._test_retry_exception(req503, exc503)

    def test_process_exception_twistederrors(self):
        for exc in (ServerTimeoutError, DNSLookupError, ConnectionRefusedError, ConnectionDone, ConnectError, ConnectionLost):
            req = Request('http://www.scrapytest.org/%s' % exc.__name__)
            self._test_retry_exception(req, exc())

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
