import logging
from testfixtures import LogCapture
from unittest import TestCase

import pytest

from scrapy.downloadermiddlewares.cookies import CookiesMiddleware
from scrapy.downloadermiddlewares.defaultheaders import DefaultHeadersMiddleware
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.exceptions import NotConfigured
from scrapy.http import Response, Request
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler


class CookiesMiddlewareTest(TestCase):

    def assertCookieValEqual(self, first, second, msg=None):
        def split_cookies(cookies):
            return sorted([s.strip() for s in to_bytes(cookies).split(b";")])
        return self.assertEqual(split_cookies(first), split_cookies(second), msg=msg)

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = CookiesMiddleware()
        self.redirect_middleware = RedirectMiddleware(settings=Settings())

    def tearDown(self):
        del self.mw
        del self.redirect_middleware

    def test_basic(self):
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        assert 'Cookie' not in req.headers

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/sub1/')
        assert self.mw.process_request(req2, self.spider) is None
        self.assertEqual(req2.headers.get('Cookie'), b"C1=value1")

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
        with LogCapture(
            'scrapy.downloadermiddlewares.cookies',
            propagate=False,
            level=logging.DEBUG,
        ) as log:
            req = Request('http://scrapytest.org/')
            res = Response('http://scrapytest.org/', headers={'Set-Cookie': 'C1=value1; path=/'})
            mw.process_response(req, res, crawler.spider)
            req2 = Request('http://scrapytest.org/sub1/')
            mw.process_request(req2, crawler.spider)

            log.check(
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
        with LogCapture(
            'scrapy.downloadermiddlewares.cookies',
            propagate=False,
            level=logging.DEBUG,
        ) as log:
            req = Request('http://scrapytest.org/')
            res = Response('http://scrapytest.org/', headers={'Set-Cookie': 'C1=value1; path=/'})
            mw.process_response(req, res, crawler.spider)
            req2 = Request('http://scrapytest.org/sub1/')
            mw.process_request(req2, crawler.spider)

            log.check()

    def test_do_not_break_on_non_utf8_header(self):
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        assert 'Cookie' not in req.headers

        headers = {'Set-Cookie': b'C1=in\xa3valid; path=/', 'Other': b'ignore\xa3me'}
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
        res = Response(
            'http://scrapytest.org/dontmerge',
            headers={'Set-Cookie': 'dont=mergeme; path=/'},
        )
        assert self.mw.process_response(req, res, self.spider) is res

        # check that cookies are merged back
        req = Request('http://scrapytest.org/mergeme')
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers.get('Cookie'), b'C1=value1')

        # check that cookies are merged when dont_merge_cookies is passed as 0
        req = Request('http://scrapytest.org/mergeme', meta={'dont_merge_cookies': 0})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers.get('Cookie'), b'C1=value1')

    def test_complex_cookies(self):
        # merge some cookies into jar
        cookies = [
            {'name': 'C1', 'value': 'value1', 'path': '/foo', 'domain': 'scrapytest.org'},
            {'name': 'C2', 'value': 'value2', 'path': '/bar', 'domain': 'scrapytest.org'},
            {'name': 'C3', 'value': 'value3', 'path': '/foo', 'domain': 'scrapytest.org'},
            {'name': 'C4', 'value': 'value4', 'path': '/foo', 'domain': 'scrapy.org'},
        ]

        req = Request('http://scrapytest.org/', cookies=cookies)
        self.mw.process_request(req, self.spider)

        # embed C1 and C3 for scrapytest.org/foo
        req = Request('http://scrapytest.org/foo')
        self.mw.process_request(req, self.spider)
        assert req.headers.get('Cookie') in (b'C1=value1; C3=value3', b'C3=value3; C1=value1')

        # embed C2 for scrapytest.org/bar
        req = Request('http://scrapytest.org/bar')
        self.mw.process_request(req, self.spider)
        self.assertEqual(req.headers.get('Cookie'), b'C2=value2')

        # embed nothing for scrapytest.org/baz
        req = Request('http://scrapytest.org/baz')
        self.mw.process_request(req, self.spider)
        assert 'Cookie' not in req.headers

    def test_merge_request_cookies(self):
        req = Request('http://scrapytest.org/', cookies={'galleta': 'salada'})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers.get('Cookie'), b'galleta=salada')

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/sub1/')
        assert self.mw.process_request(req2, self.spider) is None

        self.assertCookieValEqual(req2.headers.get('Cookie'), b"C1=value1; galleta=salada")

    def test_cookiejar_key(self):
        req = Request(
            'http://scrapytest.org/',
            cookies={'galleta': 'salada'},
            meta={'cookiejar': "store1"},
        )
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers.get('Cookie'), b'galleta=salada')

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers, request=req)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/', meta=res.meta)
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers.get('Cookie'), b'C1=value1; galleta=salada')

        req3 = Request(
            'http://scrapytest.org/',
            cookies={'galleta': 'dulce'},
            meta={'cookiejar': "store2"},
        )
        assert self.mw.process_request(req3, self.spider) is None
        self.assertEqual(req3.headers.get('Cookie'), b'galleta=dulce')

        headers = {'Set-Cookie': 'C2=value2; path=/'}
        res2 = Response('http://scrapytest.org/', headers=headers, request=req3)
        assert self.mw.process_response(req3, res2, self.spider) is res2

        req4 = Request('http://scrapytest.org/', meta=res2.meta)
        assert self.mw.process_request(req4, self.spider) is None
        self.assertCookieValEqual(req4.headers.get('Cookie'), b'C2=value2; galleta=dulce')

        # cookies from hosts with port
        req5_1 = Request('http://scrapytest.org:1104/')
        assert self.mw.process_request(req5_1, self.spider) is None

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res5_1 = Response('http://scrapytest.org:1104/', headers=headers, request=req5_1)
        assert self.mw.process_response(req5_1, res5_1, self.spider) is res5_1

        req5_2 = Request('http://scrapytest.org:1104/some-redirected-path')
        assert self.mw.process_request(req5_2, self.spider) is None
        self.assertEqual(req5_2.headers.get('Cookie'), b'C1=value1')

        req5_3 = Request('http://scrapytest.org/some-redirected-path')
        assert self.mw.process_request(req5_3, self.spider) is None
        self.assertEqual(req5_3.headers.get('Cookie'), b'C1=value1')

        # skip cookie retrieval for not http request
        req6 = Request('file:///scrapy/sometempfile')
        assert self.mw.process_request(req6, self.spider) is None
        self.assertEqual(req6.headers.get('Cookie'), None)

    def test_local_domain(self):
        request = Request("http://example-host/", cookies={'currencyCookie': 'USD'})
        assert self.mw.process_request(request, self.spider) is None
        self.assertIn('Cookie', request.headers)
        self.assertEqual(b'currencyCookie=USD', request.headers['Cookie'])

    @pytest.mark.xfail(
        reason="Cookie header is not currently being processed",
        strict=True,
    )
    def test_keep_cookie_from_default_request_headers_middleware(self):
        DEFAULT_REQUEST_HEADERS = dict(Cookie='default=value; asdf=qwerty')
        mw_default_headers = DefaultHeadersMiddleware(DEFAULT_REQUEST_HEADERS.items())
        # overwrite with values from 'cookies' request argument
        req1 = Request('http://example.org', cookies={'default': 'something'})
        assert mw_default_headers.process_request(req1, self.spider) is None
        assert self.mw.process_request(req1, self.spider) is None
        self.assertCookieValEqual(req1.headers['Cookie'], b'default=something; asdf=qwerty')
        # keep both
        req2 = Request('http://example.com', cookies={'a': 'b'})
        assert mw_default_headers.process_request(req2, self.spider) is None
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers['Cookie'], b'default=value; a=b; asdf=qwerty')

    @pytest.mark.xfail(
        reason="Cookie header is not currently being processed",
        strict=True,
    )
    def test_keep_cookie_header(self):
        # keep only cookies from 'Cookie' request header
        req1 = Request('http://scrapytest.org', headers={'Cookie': 'a=b; c=d'})
        assert self.mw.process_request(req1, self.spider) is None
        self.assertCookieValEqual(req1.headers['Cookie'], 'a=b; c=d')
        # keep cookies from both 'Cookie' request header and 'cookies' keyword
        req2 = Request('http://scrapytest.org', headers={'Cookie': 'a=b; c=d'}, cookies={'e': 'f'})
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers['Cookie'], 'a=b; c=d; e=f')
        # overwrite values from 'Cookie' request header with 'cookies' keyword
        req3 = Request(
            'http://scrapytest.org',
            headers={'Cookie': 'a=b; c=d'},
            cookies={'a': 'new', 'e': 'f'},
        )
        assert self.mw.process_request(req3, self.spider) is None
        self.assertCookieValEqual(req3.headers['Cookie'], 'a=new; c=d; e=f')

    def test_request_cookies_encoding(self):
        # 1) UTF8-encoded bytes
        req1 = Request('http://example.org', cookies={'a': 'á'.encode('utf8')})
        assert self.mw.process_request(req1, self.spider) is None
        self.assertCookieValEqual(req1.headers['Cookie'], b'a=\xc3\xa1')

        # 2) Non UTF8-encoded bytes
        req2 = Request('http://example.org', cookies={'a': 'á'.encode('latin1')})
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers['Cookie'], b'a=\xc3\xa1')

        # 3) String
        req3 = Request('http://example.org', cookies={'a': 'á'})
        assert self.mw.process_request(req3, self.spider) is None
        self.assertCookieValEqual(req3.headers['Cookie'], b'a=\xc3\xa1')

    @pytest.mark.xfail(
        reason="Cookie header is not currently being processed",
        strict=True,
    )
    def test_request_headers_cookie_encoding(self):
        # 1) UTF8-encoded bytes
        req1 = Request('http://example.org', headers={'Cookie': 'a=á'.encode('utf8')})
        assert self.mw.process_request(req1, self.spider) is None
        self.assertCookieValEqual(req1.headers['Cookie'], b'a=\xc3\xa1')

        # 2) Non UTF8-encoded bytes
        req2 = Request('http://example.org', headers={'Cookie': 'a=á'.encode('latin1')})
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers['Cookie'], b'a=\xc3\xa1')

        # 3) String
        req3 = Request('http://example.org', headers={'Cookie': 'a=á'})
        assert self.mw.process_request(req3, self.spider) is None
        self.assertCookieValEqual(req3.headers['Cookie'], b'a=\xc3\xa1')

    def test_invalid_cookies(self):
        """
        Invalid cookies are logged as warnings and discarded
        """
        with LogCapture(
            'scrapy.downloadermiddlewares.cookies',
            propagate=False,
            level=logging.INFO,
        ) as lc:
            cookies1 = [{'value': 'bar'}, {'name': 'key', 'value': 'value1'}]
            req1 = Request('http://example.org/1', cookies=cookies1)
            assert self.mw.process_request(req1, self.spider) is None
            cookies2 = [{'name': 'foo'}, {'name': 'key', 'value': 'value2'}]
            req2 = Request('http://example.org/2', cookies=cookies2)
            assert self.mw.process_request(req2, self.spider) is None
            cookies3 = [{'name': 'foo', 'value': None}, {'name': 'key', 'value': ''}]
            req3 = Request('http://example.org/3', cookies=cookies3)
            assert self.mw.process_request(req3, self.spider) is None
            lc.check(
                ("scrapy.downloadermiddlewares.cookies",
                 "WARNING",
                 "Invalid cookie found in request <GET http://example.org/1>:"
                 " {'value': 'bar'} ('name' is missing)"),
                ("scrapy.downloadermiddlewares.cookies",
                 "WARNING",
                 "Invalid cookie found in request <GET http://example.org/2>:"
                 " {'name': 'foo'} ('value' is missing)"),
                ("scrapy.downloadermiddlewares.cookies",
                 "WARNING",
                 "Invalid cookie found in request <GET http://example.org/3>:"
                 " {'name': 'foo', 'value': None} ('value' is missing)"),
            )
        self.assertCookieValEqual(req1.headers['Cookie'], 'key=value1')
        self.assertCookieValEqual(req2.headers['Cookie'], 'key=value2')
        self.assertCookieValEqual(req3.headers['Cookie'], 'key=')

    def test_primitive_type_cookies(self):
        # Boolean
        req1 = Request('http://example.org', cookies={'a': True})
        assert self.mw.process_request(req1, self.spider) is None
        self.assertCookieValEqual(req1.headers['Cookie'], b'a=True')

        # Float
        req2 = Request('http://example.org', cookies={'a': 9.5})
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers['Cookie'], b'a=9.5')

        # Integer
        req3 = Request('http://example.org', cookies={'a': 10})
        assert self.mw.process_request(req3, self.spider) is None
        self.assertCookieValEqual(req3.headers['Cookie'], b'a=10')

        # String
        req4 = Request('http://example.org', cookies={'a': 'b'})
        assert self.mw.process_request(req4, self.spider) is None
        self.assertCookieValEqual(req4.headers['Cookie'], b'a=b')


class UserSetCookieDomainTest(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = CookiesMiddleware()
        self.redirect_middleware = RedirectMiddleware(settings=Settings())

    def tearDown(self):
        del self.mw
        del self.redirect_middleware

    def _test_followup(
        self,
        url1,
        url2,
        *,
        input_cookies,
        output_cookies,
    ):
        request1 = Request(url1, cookies=input_cookies)
        self.mw.process_request(request1, self.spider)

        request2 = Request(url2)
        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, output_cookies)

    def _test_redirect(
        self,
        from_url,
        to_url,
        *,
        input_cookies,
        output_cookies,
    ):
        original_request = Request(from_url, cookies=input_cookies)
        self.mw.process_request(original_request, self.spider)

        response = Response(
            from_url,
            status=301,
            headers={
                'Location': to_url,
            },
        )
        self.assertEqual(
            self.mw.process_response(original_request, response, self.spider),
            response,
        )

        redirect_request = self.redirect_middleware.process_response(
            original_request,
            response,
            self.spider,
        )
        self.assertIsInstance(redirect_request, Request)

        self.mw.process_request(redirect_request, self.spider)
        redirect_cookies = redirect_request.headers.get('Cookie')
        self.assertEqual(redirect_cookies, output_cookies)

    def test_undefined_same(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies={'a': 'b'},
            output_cookies=b"a=b",
        )

    def test_undefined_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies={'a': 'b'},
            output_cookies=b"a=b",
        )

    def test_undefined_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies={'a': 'b'},
            output_cookies=b"a=b",
        )

    def test_undefined_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_undefined_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_undefined_sub(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (not even different
        domain-matching domains, i.e. subdomains, get the cookie).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_undefined_sub_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_undefined_super(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (superdomains do not
        get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_undefined_super_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_undefined_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_undefined_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies={'a': 'b'},
            output_cookies=None,
        )

    def test_none_same(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=b"a=b",
        )

    def test_none_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=b"a=b",
        )

    def test_none_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=b"a=b",
        )

    def test_none_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    def test_none_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    def test_none_sub(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (not even different
        domain-matching domains, i.e. subdomains, get the cookie).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    def test_none_sub_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    def test_none_super(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (superdomains do not
        get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    def test_none_super_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    def test_none_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    def test_none_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': None}],
            output_cookies=None,
        )

    @pytest.mark.xfail(
        reason=(
            "Python turns an empty domain attribute into a dot: "
            "https://bugs.python.org/issue33017"
        ),
        strict=True,
    )
    def test_empty_same(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=b"a=b",
        )

    @pytest.mark.xfail(
        reason=(
            "Python turns an empty domain attribute into a dot: "
            "https://bugs.python.org/issue33017"
        ),
        strict=True,
    )
    def test_empty_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=b"a=b",
        )

    @pytest.mark.xfail(
        reason=(
            "Python turns an empty domain attribute into a dot: "
            "https://bugs.python.org/issue33017"
        ),
        strict=True,
    )
    def test_empty_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=b"a=b",
        )

    def test_empty_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    def test_empty_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    def test_empty_sub(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (not even different
        domain-matching domains, i.e. subdomains, get the cookie).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    def test_empty_sub_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    def test_empty_super(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (superdomains do not
        get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    def test_empty_super_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    def test_empty_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    def test_empty_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': ''}],
            output_cookies=None,
        )

    @pytest.mark.xfail(
        reason=(
            "Python fails to ignore a dot as domain: "
            "https://bugs.python.org/issue33017"
        ),
        strict=True,
    )
    def test_dot_same(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=b"a=b",
        )

    @pytest.mark.xfail(
        reason=(
            "Python fails to ignore a dot as domain: "
            "https://bugs.python.org/issue33017"
        ),
        strict=True,
    )
    def test_dot_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=b"a=b",
        )

    @pytest.mark.xfail(
        reason=(
            "Python fails to ignore a dot as domain: "
            "https://bugs.python.org/issue33017"
        ),
        strict=True,
    )
    def test_dot_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=b"a=b",
        )

    def test_dot_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_dot_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_dot_sub(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (not even different
        domain-matching domains, i.e. subdomains, get the cookie).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_dot_sub_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_dot_super(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (superdomains do not
        get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_dot_super_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_dot_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_dot_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[{'name': 'a', 'value': 'b', 'domain': '.'}],
            output_cookies=None,
        )

    def test_same_same(self):
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_same_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_same_sub(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_sub_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_super(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (superdomains do not
        get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_same_super_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_same_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_same_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_same(self):
        self._test_followup(
            'https://cc.ak.us/a',
            'https://cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_public_suffix_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/a',
            'https://cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_public_suffix_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=b"a=b",
        )

    def test_same_public_suffix_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_sub(self):
        self._test_followup(
            'https://cc.ak.us/',
            'https://foobar.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_sub_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://foobar.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_super(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (superdomains do not
        get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://cc.ak.us/',
            'https://ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_super_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://cc.ak.us/',
            'https://lib.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_same_public_suffix_sibling_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://lib.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            output_cookies=None,
        )

    def test_sub_same(self):
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_sub_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_sub_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_sub_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    def test_sub_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=None,
        )

    # TODO: Make sure that the cookies are not applied to the initial request.
    # TODO: Find out why this test fails? Can domains not allow-list cookies
    # for their subdomains?
    def test_sub_sub(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            output_cookies=b"a=b",
        )

    # TODO: Continue writing the remaining test_sub_… scenarios.