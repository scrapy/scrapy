import unittest

from scrapy.contrib.downloadermiddleware.retry import RetryMiddleware
from scrapy.core.exceptions import HttpException
from scrapy.spider import spiders
from scrapy.http import Request, Response

class RetryTest(unittest.TestCase):
    def setUp(self):
        spiders.spider_modules = ['scrapy.tests.test_spiders']
        spiders.reload()
        self.spider = spiders.fromdomain('scrapytest.org')

    def test_process_exception(self):
        exception_404 = (Request('http://www.scrapytest.org/404'), HttpException('404', None, Response('http://www.scrapytest.org/404', body='')), self.spider)
        exception_503 = (Request('http://www.scrapytest.org/503'), HttpException('503', None, Response('http://www.scrapytest.org/503', body='')), self.spider)

        mw = RetryMiddleware()
        mw.retry_times = 1

        self.assertTrue(mw.process_exception(*exception_404) is None)

        self.assertTrue(isinstance(mw.process_exception(*exception_503), Request))
        self.assertTrue(mw.process_exception(*exception_503) is None)

if __name__ == "__main__":
    unittest.main()
