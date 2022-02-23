import logging
from testfixtures import LogCapture
from unittest import TestCase

import pytest

from scrapy.downloadermiddlewares.cookies import (
    CookiesMiddleware,
    cookies_to_set_cookie_list,
)
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
                (
                    "scrapy.downloadermiddlewares.cookies",
                    "WARNING",
                    (
                        "In request <GET http://example.org/1>: Key 'name' "
                        "missing in cookie {'value': 'bar'}"
                    ),
                ),
                (
                    "scrapy.downloadermiddlewares.cookies",
                    "WARNING",
                    (
                        "In request <GET http://example.org/2>: Key 'value' "
                        "missing in cookie {'name': 'foo'}"
                    ),
                ),
                (
                    "scrapy.downloadermiddlewares.cookies",
                    "WARNING",
                    (
                        "In request <GET http://example.org/3>: Key 'value' "
                        "missing in cookie {'name': 'foo', 'value': None}"
                    ),
                ),
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


class CookieDomainTest:
    other_domain = 'example.com'

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
        cookies1,
        cookies2,
    ):
        request1 = Request(url1, cookies=self.input_cookies)
        self.mw.process_request(request1, self.spider)
        cookies = request1.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies1 else None)

        request2 = Request(url2)
        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies2 else None)

    def _test_redirect(
        self,
        from_url,
        to_url,
        *,
        cookies1,
        cookies2,
    ):
        request1 = Request(from_url, cookies=self.input_cookies)
        self.mw.process_request(request1, self.spider)
        cookies = request1.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies1 else None)

        response = Response(
            from_url,
            status=301,
            headers={
                'Location': to_url,
            },
        )
        self.assertEqual(
            self.mw.process_response(request1, response, self.spider),
            response,
        )

        request2 = self.redirect_middleware.process_response(
            request1,
            response,
            self.spider,
        )
        self.assertIsInstance(request2, Request)

        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies2 else None)

    def test_same(self):
        self._test_followup(
            f'https://{self.domain}/a',
            f'https://{self.domain}/b',
            cookies1=True,
            cookies2=True,
        )

    def test_same_redirect_absolute(self):
        self._test_redirect(
            f'https://{self.domain}/a',
            f'https://{self.domain}/b',
            cookies1=True,
            cookies2=True,
        )

    def test_same_redirect_relative(self):
        self._test_redirect(
            f'https://{self.domain}/a',
            '/b',
            cookies1=True,
            cookies2=True,
        )

    def test_other(self):
        self._test_followup(
            f'https://{self.domain}/',
            f'https://{self.other_domain}',
            cookies1=True,
            cookies2=False,
        )

    def test_other_redirect(self):
        self._test_redirect(
            f'https://{self.domain}/',
            f'https://{self.other_domain}',
            cookies1=True,
            cookies2=False,
        )

    def test_sub(self):
        self._test_followup(
            f'https://{self.domain}/',
            f'https://a.{self.domain}/',
            cookies1=True,
            cookies2=getattr(self, 'subdomain_cookies', False),
        )

    def test_sub_redirect(self):
        self._test_redirect(
            f'https://{self.domain}/',
            f'https://a.{self.domain}/',
            cookies1=True,
            cookies2=getattr(self, 'subdomain_cookies', False),
        )

    def test_super(self):
        if not hasattr(self, 'super_domain'):
            self.skipTest('No super domain defined')
        self._test_followup(
            f'https://{self.domain}/',
            f'https://{self.super_domain}/',
            cookies1=True,
            cookies2=False,
        )

    def test_super_redirect(self):
        if not hasattr(self, 'super_domain'):
            self.skipTest('No super domain defined')
        self._test_redirect(
            f'https://{self.domain}/',
            f'https://{self.super_domain}/',
            cookies1=True,
            cookies2=False,
        )

    def test_sibling(self):
        if not hasattr(self, 'sibling_domain'):
            self.skipTest('No sibling domain defined')
        self._test_followup(
            f'https://{self.domain}/',
            f'https://{self.sibling_domain}/',
            cookies1=True,
            cookies2=False,
        )

    def test_sibling_redirect(self):
        if not hasattr(self, 'sibling_domain'):
            self.skipTest('No sibling domain defined')
        self._test_redirect(
            f'https://{self.domain}/',
            f'https://{self.sibling_domain}/',
            cookies1=True,
            cookies2=False,
        )


class RegularDomain:
    super_domain = 'toscrape.com'
    domain = 'books.toscrape.com'
    sibling_domain = 'quotes.toscrape.com'


class PublicDomain:
    super_domain = 'ak.us'
    domain = 'cc.ak.us'
    sibling_domain = 'lib.ak.us'


class NoDotDomain:  # local domain
    domain = 'example-host'


class DictCookies:
    input_cookies = {'a': 'b'}


class NoneCookies:
    input_cookies = [{'name': 'a', 'value': 'b', 'domain': None}]


class EmptyCookies:
    input_cookies = [{'name': 'a', 'value': 'b', 'domain': ''}]


class DotCookies:
    input_cookies = [{'name': 'a', 'value': 'b', 'domain': '.'}]


class DomainCookies:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.input_cookies = [
            {'name': 'a', 'value': 'b', 'domain': self.domain}
        ]

        # If the request domain is used as cookie domain, it means that the
        # cookie must be sent to that domain and any subdomain.
        #
        # That is, unless the specified domain is a public suffix, in which
        # case its cookies are restricted to the request domain nonetheless.
        self.subdomain_cookies = not isinstance(self, PublicDomain)


class DotDomainCookies(DomainCookies):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.input_cookies = [
            {'name': 'a', 'value': 'b', 'domain': f'.{self.domain}'}
        ]


class DictRegularCookieDomainTest(
    DictCookies,
    RegularDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DictPublicCookieDomainTest(
    DictCookies,
    PublicDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DictNoDotCookieDomainTest(
    DictCookies,
    NoDotDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class NoneRegularCookieDomainTest(
    NoneCookies,
    RegularDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class NonePublicCookieDomainTest(
    NoneCookies,
    PublicDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class NoneNoDotCookieDomainTest(
    NoneCookies,
    NoDotDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class EmptyRegularCookieDomainTest(
    EmptyCookies,
    RegularDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class EmptyPublicCookieDomainTest(
    EmptyCookies,
    PublicDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class EmptyNoDotCookieDomainTest(
    EmptyCookies,
    NoDotDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DotRegularCookieDomainTest(
    DotCookies,
    RegularDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DotPublicCookieDomainTest(
    DotCookies,
    PublicDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DotNoDotCookieDomainTest(
    DotCookies,
    NoDotDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DomainRegularCookieDomainTest(
    DomainCookies,
    RegularDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DomainPublicCookieDomainTest(
    DomainCookies,
    PublicDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DomainNoDotCookieDomainTest(
    DomainCookies,
    NoDotDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DotDomainRegularCookieDomainTest(
    DotDomainCookies,
    RegularDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DotDomainPublicCookieDomainTest(
    DotDomainCookies,
    PublicDomain,
    CookieDomainTest,
    TestCase,
):
    pass


class DotDomainNoDotCookieDomainTest(
    DotDomainCookies,
    NoDotDomain,
    CookieDomainTest,
    TestCase,
):
    pass

# TODO:
#
# Complete tests about cookies:
#
# 1.  Continue migrating the code below to the class-based approach above.
#
# 2.  Extend tests to take into account the following scenarios:
#
#     -   Cookies set by users through the Cookie header, instead of the
#         cookies parameter of requests.
#
#         See https://github.com/scrapy/scrapy/issues/1992
#
#     -   Cookies set by users through the Set-Cookie header, instead of the
#         cookies parameter of requests.
#
#         I (Gallaecio) am not sure what the expected behavior should be here.
#
#     -   The 2 scenarios above when the cookie middleware is disabled.
#
#     -   Maybe we should also consider scenarios where
#         dont_merge_cookies=False is involved.
#
# 3.  Find out how cookies are supposed to work with IP addresses, and add
#     tests for those scenarios.
#
# 4.  Test uppercase-lowercase combinations of the cookie domain (they are
#     supposed to be normalized to lowercase).
#
# 5.  Test the behavior with multiple domains set in a cookie. The last one
#     takes precedence. In most browsers I believe a last domain with an empty
#     value means the domain is interpreted as being unset (instead of a
#     previous, non-empty value being taken).
#
# 6.  Cover with tests what https://github.com/scrapy/scrapy/pull/4812 aims to
#     address.
#
# 7.  Make sure that foobar.local and foobar do not get the same cookies
#     unintendedly. This would be a bug of my initial attempt to bypass the
#     shortcomings of the Python standard library for the handling of domains
#     without a period. Maybe we need to append .local to hosts that end in
#     .local already and have only 1 dot.
#
# Make sure to include descriptions and references to the standard and any
# other relevant sources in the corresponding components of the tests.
#
# Also, consider providing basic documentation about cookies, and links to
# upstream documentation, so that users understand e.g. the effects of setting
# a domain for a cookie (which unintuitively is less restrictive that not
# setting a domain).


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
        cookies1,
        cookies2,
    ):
        request1 = Request(url1, cookies=input_cookies)
        self.mw.process_request(request1, self.spider)
        cookies = request1.headers.get('Cookie')
        self.assertEqual(cookies, cookies1)

        request2 = Request(url2)
        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, cookies2)

    def _test_redirect(
        self,
        from_url,
        to_url,
        *,
        input_cookies,
        cookies1,
        cookies2,
    ):
        request1 = Request(from_url, cookies=input_cookies)
        self.mw.process_request(request1, self.spider)
        cookies = request1.headers.get('Cookie')
        self.assertEqual(cookies, cookies1)

        response = Response(
            from_url,
            status=301,
            headers={
                'Location': to_url,
            },
        )
        self.assertEqual(
            self.mw.process_response(request1, response, self.spider),
            response,
        )

        request2 = self.redirect_middleware.process_response(
            request1,
            response,
            self.spider,
        )
        self.assertIsInstance(request2, Request)

        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, cookies2)

    def test_sub_same(self):
        """If the specified cookie domain does not domain-match the request
        domain, the cookie must be ignored. Domain-matching means being the
        same domain or a superdomain, so specifing a subdomain must cause the
        cookie to be ignored."""
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
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
            cookies1=None,
            cookies2=None,
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
            cookies1=None,
            cookies2=None,
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
            cookies1=None,
            cookies2=None,
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
            cookies1=None,
            cookies2=None,
        )

    def test_sub_sub_same(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_sub_same_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_sub_other(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'quotes.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_sub_other_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'quotes.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_super(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_super_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_same(self):
        """If the specified cookie domain does not domain-match the request
        domain, the cookie must be ignored. Domain-matching means being the
        same domain or a superdomain, so specifing a subdomain must cause the
        cookie to be ignored."""
        self._test_followup(
            'https://cc.ak.us/a',
            'https://cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/a',
            'https://cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_sub_same(self):
        self._test_followup(
            'https://cc.ak.us/',
            'https://foobar.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_sub_same_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://foobar.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_sub_other(self):
        self._test_followup(
            'https://cc.ak.us/',
            'https://barfoo.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_sub_other_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://barfoo.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_super(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'b.a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_super_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'b.a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://cc.ak.us/',
            'https://lib.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_sub_public_suffix_sibling_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://lib.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_same(self):
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_sub_same(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_sub_same_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_sub_other(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.quotes.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_sub_other_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.quotes.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_super(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_super_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_sibling(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.bad.books.toscrape.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_same(self):
        """If the specified cookie domain does not domain-match the request
        domain, the cookie must be ignored. Domain-matching means being the
        same domain or a superdomain, so specifing a subdomain must cause the
        cookie to be ignored."""
        self._test_followup(
            'https://cc.ak.us/a',
            'https://cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/a',
            'https://cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_sub_same(self):
        self._test_followup(
            'https://cc.ak.us/',
            'https://foobar.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_sub_same_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://foobar.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_sub_other(self):
        self._test_followup(
            'https://cc.ak.us/',
            'https://barfoo.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_sub_other_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://barfoo.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.foobar.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_super(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.b.a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_super_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.b.a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_sibling(self):
        """If a cookie is set without an explicit domain value, it is
        restricted to the domain for which is has been set (sibling subdomains
        do not get the cookie either).

        https://datatracker.ietf.org/doc/html/rfc6265#section-5.3
        """
        self._test_followup(
            'https://cc.ak.us/',
            'https://lib.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsub_public_suffix_sibling_redirect(self):
        self._test_redirect(
            'https://cc.ak.us/',
            'https://lib.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.a.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_same(self):
        self._test_followup(
            'https://books.toscrape.com/a',
            'https://books.toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://books.toscrape.com/a',
            'https://books.toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://books.toscrape.com/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_super_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_super_sub_same(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://a.books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_sub_same_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://a.books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_sub_other(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_super_sub_other_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_super_super_same(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_super_same_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_super_sub(self):
        self._test_followup(
            'https://a.books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_super_super_sub_redirect(self):
        self._test_redirect(
            'https://a.books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'books.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_super_super_super(self):
        self._test_followup(
            'https://a.books.toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_super_super_redirect(self):
        self._test_redirect(
            'https://a.books.toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_sibling(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_super_public_suffix_same(self):
        self._test_followup(
            'https://a.cc.ak.us/a',
            'https://a.cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://a.cc.ak.us/a',
            'https://a.cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://a.cc.ak.us/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_sub_same(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://b.a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_sub_same_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://b.a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_sub_other(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_sub_other_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_super_same(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_super_same_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_super_sub(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_super_sub_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_super_super(self):
        self._test_followup(
            'https://b.a.cc.ak.us/',
            'https://a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_super_super_redirect(self):
        self._test_redirect(
            'https://b.a.cc.ak.us/',
            'https://a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_sibling(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://b.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_super_public_suffix_sibling_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://b.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_same(self):
        self._test_followup(
            'https://books.toscrape.com/a',
            'https://books.toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://books.toscrape.com/a',
            'https://books.toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://books.toscrape.com/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_dotsuper_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_dotsuper_sub_same(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://a.books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_sub_same_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://a.books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_sub_other(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_dotsuper_sub_other_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_dotsuper_super_same(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_super_same_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_super_sub(self):
        self._test_followup(
            'https://a.books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_dotsuper_super_sub_redirect(self):
        self._test_redirect(
            'https://a.books.toscrape.com/',
            'https://toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.books.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=None,
        )

    def test_dotsuper_super_super(self):
        self._test_followup(
            'https://a.books.toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_super_super_redirect(self):
        self._test_redirect(
            'https://a.books.toscrape.com/',
            'https://books.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_sibling(self):
        self._test_followup(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_sibling_redirect(self):
        self._test_redirect(
            'https://books.toscrape.com/',
            'https://quotes.toscrape.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.toscrape.com'}
            ],
            cookies1=b'a=b',
            cookies2=b'a=b',
        )

    def test_dotsuper_public_suffix_same(self):
        self._test_followup(
            'https://a.cc.ak.us/a',
            'https://a.cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_same_redirect_absolute(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://a.cc.ak.us/a',
            'https://a.cc.ak.us/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_same_redirect_relative(self):
        """If a request to a domain sets some cookies, follow-up requests to
        the same domain include those cookies."""
        self._test_redirect(
            'https://a.cc.ak.us/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_other(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_other_redirect(self):
        """If a request to a domain sets some cookies, follow-up requests to
        a different domain do not include those cookies."""
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_sub_same(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://b.a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_sub_same_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://b.a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_sub_other(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_sub_other_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_super_same(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_super_same_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_super_sub(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_super_sub_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_super_super(self):
        self._test_followup(
            'https://b.a.cc.ak.us/',
            'https://a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_super_super_redirect(self):
        self._test_redirect(
            'https://b.a.cc.ak.us/',
            'https://a.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_sibling(self):
        self._test_followup(
            'https://a.cc.ak.us/',
            'https://b.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotsuper_public_suffix_sibling_redirect(self):
        self._test_redirect(
            'https://a.cc.ak.us/',
            'https://b.cc.ak.us/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.cc.ak.us'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_other_same(self):
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_other_same_redirect_absolute(self):
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_other_same_redirect_relative(self):
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_other_other(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_other_other_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': 'example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotother_same(self):
        self._test_followup(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotother_same_redirect_absolute(self):
        self._test_redirect(
            'https://toscrape.com/a',
            'https://toscrape.com/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotother_same_redirect_relative(self):
        self._test_redirect(
            'https://toscrape.com/a',
            '/b',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotother_other(self):
        self._test_followup(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )

    def test_dotother_other_redirect(self):
        self._test_redirect(
            'https://toscrape.com/',
            'https://example.com/',
            input_cookies=[
                {'name': 'a', 'value': 'b', 'domain': '.example.com'}
            ],
            cookies1=None,
            cookies2=None,
        )


class ServerCookieDomainTest(UserSetCookieDomainTest):

    def _test_followup(
        self,
        url1,
        url2,
        *,
        input_cookies,
        cookies1,
        cookies2,
    ):
        del cookies1  # Does not apply on server-set cookies

        request1 = Request(url1)
        self.mw.process_request(request1, self.spider)

        headers = {
            'Set-Cookie': cookies_to_set_cookie_list(input_cookies),
        }
        response = Response(url1, status=200, headers=headers)
        self.assertEqual(
            self.mw.process_response(request1, response, self.spider),
            response,
        )

        request2 = Request(url2)
        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, cookies2)

    def _test_redirect(
        self,
        from_url,
        to_url,
        *,
        input_cookies,
        cookies1,
        cookies2,
    ):
        del cookies1  # Does not apply on server-set cookies

        request1 = Request(from_url)
        self.mw.process_request(request1, self.spider)

        headers = {
            'Location': to_url,
            'Set-Cookie': cookies_to_set_cookie_list(input_cookies),
        }
        response = Response(from_url, status=301, headers=headers)
        self.assertEqual(
            self.mw.process_response(request1, response, self.spider),
            response,
        )

        request2 = self.redirect_middleware.process_response(
            request1,
            response,
            self.spider,
        )
        self.assertIsInstance(request2, Request)

        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, cookies2)
