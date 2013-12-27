from unittest import TestCase

from scrapy.http import Response, Request
from scrapy.spider import Spider
from scrapy.contrib.spidermiddleware.httperror import HttpErrorMiddleware, HttpError
from scrapy.settings import Settings


class TestHttpErrorMiddleware(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = HttpErrorMiddleware(Settings({}))
        self.req = Request('http://scrapytest.org')

        self.res200 = Response('http://scrapytest.org', status=200)
        self.res200.request = self.req
        self.res404 = Response('http://scrapytest.org', status=404)
        self.res404.request = self.req

    def test_process_spider_input(self):
        self.assertEquals(None,
                self.mw.process_spider_input(self.res200, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, self.res404, self.spider)

    def test_process_spider_exception(self):
        self.assertEquals([],
                self.mw.process_spider_exception(self.res404, \
                        HttpError(self.res404), self.spider))
        self.assertEquals(None,
                self.mw.process_spider_exception(self.res404, \
                        Exception(), self.spider))

    def test_handle_httpstatus_list(self):
        res = self.res404.copy()
        res.request = Request('http://scrapytest.org',
                              meta={'handle_httpstatus_list': [404]})
        self.assertEquals(None,
            self.mw.process_spider_input(res, self.spider))

        self.spider.handle_httpstatus_list = [404]
        self.assertEquals(None,
            self.mw.process_spider_input(self.res404, self.spider))

class TestHttpErrorMiddlewareSettings(TestCase):
    """Similar test, but with settings"""

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = HttpErrorMiddleware(Settings({'HTTPERROR_ALLOWED_CODES': (402,)}))
        self.req = Request('http://scrapytest.org')

        self.res200 = Response('http://scrapytest.org', status=200)
        self.res200.request = self.req
        self.res404 = Response('http://scrapytest.org', status=404)
        self.res404.request = self.req
        self.res402 = Response('http://scrapytest.org', status=402)
        self.res402.request = self.req

    def test_process_spider_input(self):
        self.assertEquals(None,
                self.mw.process_spider_input(self.res200, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, self.res404, self.spider)
        self.assertEquals(None,
                self.mw.process_spider_input(self.res402, self.spider))

    def test_meta_overrides_settings(self):
        request = Request('http://scrapytest.org',
                              meta={'handle_httpstatus_list': [404]})
        res404 = self.res404.copy()
        res404.request = request
        res402 = self.res402.copy()
        res402.request = request

        self.assertEquals(None,
            self.mw.process_spider_input(res404, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, res402, self.spider)

    def test_spider_override_settings(self):
        self.spider.handle_httpstatus_list = [404]
        self.assertEquals(None,
            self.mw.process_spider_input(self.res404, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, self.res402, self.spider)

class TestHttpErrorMiddlewareHandleAll(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = HttpErrorMiddleware(Settings({'HTTPERROR_ALLOW_ALL': True}))
        self.req = Request('http://scrapytest.org')

        self.res200 = Response('http://scrapytest.org', status=200)
        self.res200.request = self.req
        self.res404 = Response('http://scrapytest.org', status=404)
        self.res404.request = self.req
        self.res402 = Response('http://scrapytest.org', status=402)
        self.res402.request = self.req

    def test_process_spider_input(self):
        self.assertEquals(None,
                self.mw.process_spider_input(self.res200, self.spider))
        self.assertEquals(None,
                self.mw.process_spider_input(self.res404, self.spider))

    def test_meta_overrides_settings(self):
        request = Request('http://scrapytest.org',
                              meta={'handle_httpstatus_list': [404]})
        res404 = self.res404.copy()
        res404.request = request
        res402 = self.res402.copy()
        res402.request = request

        self.assertEquals(None,
            self.mw.process_spider_input(res404, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, res402, self.spider)

