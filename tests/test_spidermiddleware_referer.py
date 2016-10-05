from unittest import TestCase

from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.spidermiddlewares.referer import RefererMiddleware


class TestRefererMiddleware(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = RefererMiddleware()

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')
        reqs = [Request('http://scrapytest.org/')]

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out[0].headers.get('Referer'),
                          b'http://scrapytest.org')

    def test_policy_default(self):
        """
        Based on https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade

        with some additional filtering of s3://
        """
        # a) https:// --> https://  -- include Referer header
        origin = Response('https://example.com/')
        target = Request('https://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'),
                          b'https://example.com/')

        # b.1) http:// --> http://  -- include Referer header
        origin = Response('http://example.com/')
        target = Request('http://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'),
                          b'http://example.com/')

        # b.2) http:// --> https://  -- include Referer header
        origin = Response('http://example.com/')
        target = Request('https://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'),
                          b'http://example.com/')

        # c) https:// --> http://  -- Referer header NOT sent
        origin = Response('https://example.com/')
        target = Request('http://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'), None)

    def test_policy_default_no_credentials_leak(self):
        origin = Response('http://user:password@example.com/')
        target = Request('https://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'),
                          b'http://example.com/')

    def test_policy_default_file_no_referrer_leak(self):
        # file:// --> https://  -- Referrer NOT sent
        origin = Response('file:///home/path/to/somefile.html')
        target = Request('https://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'), None)

        # file:// --> http://  -- Referrer NOT sent
        origin = Response('file:///home/path/to/somefile.html')
        target = Request('http://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'), None)

    def test_policy_default_s3_no_referrer_leak(self):
        # s3:// --> https://  -- Referrer NOT sent
        origin = Response('s3://mybucket/path/to/data.csv')
        target = Request('https://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'), None)

        # s3:// --> http://  -- Referrer NOT sent
        origin = Response('s3://mybucket/path/to/data.csv')
        target = Request('http://scrapy.org/')

        out = list(self.mw.process_spider_output(origin, [target], self.spider))
        self.assertEquals(out[0].headers.get('Referer'), None)
