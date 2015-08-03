import re
import logging
from unittest import TestCase
from testfixtures import LogCapture

from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from scrapy.exceptions import NotConfigured
from scrapy.downloadermiddlewares.cookies import CookiesMiddleware


class CookiesMiddlewareTest(TestCase):

    def assertCookieValEqual(self, first, second, msg=None):
        cookievaleq = lambda cv: re.split(';\s*', cv.decode('latin1'))
        return self.assertEqual(
            sorted(cookievaleq(first)),
            sorted(cookievaleq(second)), msg)

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = CookiesMiddleware()

    def tearDown(self):
        del self.mw

    def test_basic(self):
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        assert 'Cookie' not in req.headers

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/sub1/')
        assert self.mw.process_request(req2, self.spider) is None
        self.assertEquals(req2.headers.get('Cookie'), b"C1=value1")

    def test_setting_false_cookies_enabled(self):
        self.assertRaises(
            NotConfigured,
            CookiesMiddleware.from_crawler,
            get_crawler(settings_dict={'COOKIES_ENABLED': False})
        )

    def test_setting_default_cookies_enabled(self):
        self.assertIsInstance(
            CookiesMiddleware.from_crawler(get_crawler()),
            CookiesMiddleware
        )

    def test_setting_true_cookies_enabled(self):
        self.assertIsInstance(
            CookiesMiddleware.from_crawler(
                get_crawler(settings_dict={'COOKIES_ENABLED': True})
            ),
            CookiesMiddleware
        )

    def test_setting_enabled_cookies_debug(self):
        crawler = get_crawler(settings_dict={'COOKIES_DEBUG': True})
        mw = CookiesMiddleware.from_crawler(crawler)
        with LogCapture('scrapy.downloadermiddlewares.cookies',
                        propagate=False,
                        level=logging.DEBUG) as l:
            req = Request('http://scrapytest.org/')
            res = Response('http://scrapytest.org/',
                           headers={'Set-Cookie': 'C1=value1; path=/'})
            mw.process_response(req, res, crawler.spider)
            req2 = Request('http://scrapytest.org/sub1/')
            mw.process_request(req2, crawler.spider)

            l.check(
                ('scrapy.downloadermiddlewares.cookies',
                 'DEBUG',
                 'Received cookies from: <200 http://scrapytest.org/>\n'
                 'Set-Cookie: C1=value1; path=/\n'),
                ('scrapy.downloadermiddlewares.cookies',
                 'DEBUG',
                 'Sending cookies to: <GET http://scrapytest.org/sub1/>\n'
                 'Cookie: C1=value1\n'),
            )

    def test_setting_disabled_cookies_debug(self):
        crawler = get_crawler(settings_dict={'COOKIES_DEBUG': False})
        mw = CookiesMiddleware.from_crawler(crawler)
        with LogCapture('scrapy.downloadermiddlewares.cookies',
                        propagate=False,
                        level=logging.DEBUG) as l:
            req = Request('http://scrapytest.org/')
            res = Response('http://scrapytest.org/',
                           headers={'Set-Cookie': 'C1=value1; path=/'})
            mw.process_response(req, res, crawler.spider)
            req2 = Request('http://scrapytest.org/sub1/')
            mw.process_request(req2, crawler.spider)

            l.check()

    def test_do_not_break_on_non_utf8_header(self):
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        assert 'Cookie' not in req.headers

        headers = {'Set-Cookie': b'C1=in\xa3valid; path=/',
                   'Other': b'ignore\xa3me'}
        res = Response('http://scrapytest.org/', headers=headers)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/sub1/')
        assert self.mw.process_request(req2, self.spider) is None
        self.assertIn('Cookie', req2.headers)

    def test_dont_merge_cookies(self):
        # merge some cookies into jar
        headers = {'Set-Cookie': 'C1=value1; path=/'}
        req = Request('http://scrapytest.org/')
        res = Response('http://scrapytest.org/', headers=headers)
        assert self.mw.process_response(req, res, self.spider) is res

        # test Cookie header is not seted to request
        req = Request('http://scrapytest.org/dontmerge', meta={'dont_merge_cookies': 1})
        assert self.mw.process_request(req, self.spider) is None
        assert 'Cookie' not in req.headers

        # check that returned cookies are not merged back to jar
        res = Response('http://scrapytest.org/dontmerge', headers={'Set-Cookie': 'dont=mergeme; path=/'})
        assert self.mw.process_response(req, res, self.spider) is res

        # check that cookies are merged back
        req = Request('http://scrapytest.org/mergeme')
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers.get('Cookie'), b'C1=value1')

        # check that cookies are merged when dont_merge_cookies is passed as 0
        req = Request('http://scrapytest.org/mergeme', meta={'dont_merge_cookies': 0})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers.get('Cookie'), b'C1=value1')

    def test_complex_cookies(self):
        # merge some cookies into jar
        cookies = [{'name': 'C1', 'value': 'value1', 'path': '/foo', 'domain': 'scrapytest.org'},
                {'name': 'C2', 'value': 'value2', 'path': '/bar', 'domain': 'scrapytest.org'},
                {'name': 'C3', 'value': 'value3', 'path': '/foo', 'domain': 'scrapytest.org'},
                {'name': 'C4', 'value': 'value4', 'path': '/foo', 'domain': 'scrapy.org'}]


        req = Request('http://scrapytest.org/', cookies=cookies)
        self.mw.process_request(req, self.spider)

        # embed C1 and C3 for scrapytest.org/foo
        req = Request('http://scrapytest.org/foo')
        self.mw.process_request(req, self.spider)
        assert req.headers.get('Cookie') in (b'C1=value1; C3=value3', b'C3=value3; C1=value1')

        # embed C2 for scrapytest.org/bar
        req = Request('http://scrapytest.org/bar')
        self.mw.process_request(req, self.spider)
        self.assertEquals(req.headers.get('Cookie'), b'C2=value2')

        # embed nothing for scrapytest.org/baz
        req = Request('http://scrapytest.org/baz')
        self.mw.process_request(req, self.spider)
        assert 'Cookie' not in req.headers

    def test_merge_request_cookies(self):
        req = Request('http://scrapytest.org/', cookies={'galleta': 'salada'})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers.get('Cookie'), b'galleta=salada')

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/sub1/')
        assert self.mw.process_request(req2, self.spider) is None

        self.assertCookieValEqual(req2.headers.get('Cookie'), b"C1=value1; galleta=salada")

    def test_cookiejar_key(self):
        req = Request('http://scrapytest.org/', cookies={'galleta': 'salada'}, meta={'cookiejar': "store1"})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers.get('Cookie'), b'galleta=salada')

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers, request=req)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/', meta=res.meta)
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers.get('Cookie'), b'C1=value1; galleta=salada')

        req3 = Request('http://scrapytest.org/', cookies={'galleta': 'dulce'}, meta={'cookiejar': "store2"})
        assert self.mw.process_request(req3, self.spider) is None
        self.assertEquals(req3.headers.get('Cookie'), b'galleta=dulce')

        headers = {'Set-Cookie': 'C2=value2; path=/'}
        res2 = Response('http://scrapytest.org/', headers=headers, request=req3)
        assert self.mw.process_response(req3, res2, self.spider) is res2

        req4 = Request('http://scrapytest.org/', meta=res2.meta)
        assert self.mw.process_request(req4, self.spider) is None
        self.assertCookieValEqual(req4.headers.get('Cookie'), b'C2=value2; galleta=dulce')

        #cookies from hosts with port
        req5_1 = Request('http://scrapytest.org:1104/')
        assert self.mw.process_request(req5_1, self.spider) is None

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res5_1 = Response('http://scrapytest.org:1104/', headers=headers, request=req5_1)
        assert self.mw.process_response(req5_1, res5_1, self.spider) is res5_1

        req5_2 = Request('http://scrapytest.org:1104/some-redirected-path')
        assert self.mw.process_request(req5_2, self.spider) is None
        self.assertEquals(req5_2.headers.get('Cookie'), b'C1=value1')

        req5_3 = Request('http://scrapytest.org/some-redirected-path')
        assert self.mw.process_request(req5_3, self.spider) is None
        self.assertEquals(req5_3.headers.get('Cookie'), b'C1=value1')

        #skip cookie retrieval for not http request
        req6 = Request('file:///scrapy/sometempfile')
        assert self.mw.process_request(req6, self.spider) is None
        self.assertEquals(req6.headers.get('Cookie'), None)

    def test_local_domain(self):
        request = Request("http://example-host/", cookies={'currencyCookie': 'USD'})
        assert self.mw.process_request(request, self.spider) is None
        self.assertIn('Cookie', request.headers)
        self.assertEqual(b'currencyCookie=USD', request.headers['Cookie'])
