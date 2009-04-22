from __future__ import with_statement

from unittest import TestCase

from scrapy.spider import spiders
from scrapy.core.exceptions import HttpException
from scrapy.http import Response, Request
from scrapy.contrib.downloadermiddleware.cookies import CookiesMiddleware


class CookiesMiddlewareTest(TestCase):

    def setUp(self):
        spiders.spider_modules = ['scrapy.tests.test_spiders']
        spiders.reload()
        self.spider = spiders.fromdomain('scrapytest.org')
        self.mw = CookiesMiddleware()

    def tearDown(self):
        self.mw.domain_closed('scrapytest.org')
        del self.mw

    def test_basic(self):
        headers = {'Set-Cookie': 'C1=value1; path=/'}
        req = Request('http://scrapytest.org/')
        self.mw.process_request(req, self.spider)

        assert 'Cookie' not in req.headers

        res = Response('http://scrapytest.org/', headers=headers)
        self.mw.process_response(req, res, self.spider)

        #assert res.cookies

        req2 = Request('http://scrapytest.org/sub1/')
        self.mw.process_request(req2, self.spider)
        self.assertEquals(req2.headers.get('Cookie'), "C1=value1")

    def test_http_exception(self):
        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers)
        exc = HttpException(302, 'Redirect', res)

        req = Request('http://scrapytest.org/')
        self.mw.process_request(req, self.spider)
        assert 'Cookie' not in req.headers

        self.mw.process_exception(req, exc, self.spider)
        #assert exc.response.cookies

        req2 = Request('http://scrapytest.org/sub1/')
        self.mw.process_request(req2, self.spider)
        self.assertEquals(req2.headers.get('Cookie'), "C1=value1")


    def test_dont_merge_cookies(self):
        # merge some cookies into jar
        headers = {'Set-Cookie': 'C1=value1; path=/'}
        req = Request('http://scrapytest.org/')
        res = Response('http://scrapytest.org/', headers=headers)
        self.mw.process_response(req, res, self.spider)

        # test Cookie header is not seted to request
        req = Request('http://scrapytest.org/dontmerge', meta={'dont_merge_cookies': 1})
        self.mw.process_request(req, self.spider)
        assert 'Cookie' not in req.headers

        # check that returned cookies are not merged back to jar
        res = Response('http://scrapytest.org/dontmerge', headers={'Set-Cookie': 'dont=mergeme; path=/'})
        self.mw.process_response(req, res, self.spider)
        req = Request('http://scrapytest.org/mergeme')
        self.mw.process_request(req, self.spider)
        self.assertEquals(req.headers.get('Cookie'), 'C1=value1')

    def test_merge_request_cookies(self):
        req = Request('http://scrapytest.org/', cookies={'galleta': 'salada'})
        self.mw.process_request(req, self.spider)
        self.assertEquals(req.headers.get('Cookie'), 'galleta=salada')

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers)
        self.mw.process_response(req, res, self.spider)
        req2 = Request('http://scrapytest.org/sub1/')
        self.mw.process_request(req2, self.spider)
        self.assertEquals(req2.headers.get('Cookie'), "C1=value1; galleta=salada")




