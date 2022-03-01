import re
import logging
from unittest import TestCase
from testfixtures import LogCapture

from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.http import Response, Request
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from scrapy.exceptions import NotConfigured
from scrapy.downloadermiddlewares.cookies import CookiesMiddleware


def _cookie_to_set_cookie_value(cookie):
    """Given a cookie defined as a dictionary with name and value keys, and
    optional path and domain keys, return the equivalent string that can be
    associated to a ``Set-Cookie`` header."""
    decoded = {}
    for key in ("name", "value", "path", "domain"):
        if cookie.get(key) is None:
            if key in ("name", "value"):
                return
            continue
        if isinstance(cookie[key], (bool, float, int, str)):
            decoded[key] = str(cookie[key])
        else:
            try:
                decoded[key] = cookie[key].decode("utf8")
            except UnicodeDecodeError:
                decoded[key] = cookie[key].decode("latin1", errors="replace")

    cookie_str = "{}={}".format(decoded.pop('name'), decoded.pop('value'))
    for key, value in decoded.items():  # path, domain
        cookie_str += "; {}={}".format(key.capitalize(), value)
    return cookie_str


def _cookies_to_set_cookie_list(cookies):
    """Given a group of cookie defined either as a dictionary or as a list of
    dictionaries (i.e. in a format supported by the cookies parameter of
    Request), return the equivalen list of strings that can be associated to a
    ``Set-Cookie`` header."""
    if not cookies:
        return []
    if isinstance(cookies, dict):
        cookies = ({"name": k, "value": v} for k, v in cookies.items())
    return filter(
        None,
        (
            _cookie_to_set_cookie_value(cookie)
            for cookie in cookies
        )
    )


class CookiesMiddlewareTest(TestCase):

    def assertCookieValEqual(self, first, second, msg=None):
        cookievaleq = lambda cv: re.split(r';\s*', cv.decode('latin1'))
        return self.assertEqual(
            sorted(cookievaleq(first)),
            sorted(cookievaleq(second)), msg)

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
        self.assertEqual(req.headers.get('Cookie'), b'C1=value1')

        # check that cookies are merged when dont_merge_cookies is passed as 0
        req = Request('http://scrapytest.org/mergeme', meta={'dont_merge_cookies': 0})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers.get('Cookie'), b'C1=value1')

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
        req = Request('http://scrapytest.org/', cookies={'galleta': 'salada'}, meta={'cookiejar': "store1"})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers.get('Cookie'), b'galleta=salada')

        headers = {'Set-Cookie': 'C1=value1; path=/'}
        res = Response('http://scrapytest.org/', headers=headers, request=req)
        assert self.mw.process_response(req, res, self.spider) is res

        req2 = Request('http://scrapytest.org/', meta=res.meta)
        assert self.mw.process_request(req2, self.spider) is None
        self.assertCookieValEqual(req2.headers.get('Cookie'), b'C1=value1; galleta=salada')

        req3 = Request('http://scrapytest.org/', cookies={'galleta': 'dulce'}, meta={'cookiejar': "store2"})
        assert self.mw.process_request(req3, self.spider) is None
        self.assertEqual(req3.headers.get('Cookie'), b'galleta=dulce')

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
        self.assertEqual(req5_2.headers.get('Cookie'), b'C1=value1')

        req5_3 = Request('http://scrapytest.org/some-redirected-path')
        assert self.mw.process_request(req5_3, self.spider) is None
        self.assertEqual(req5_3.headers.get('Cookie'), b'C1=value1')

        #skip cookie retrieval for not http request
        req6 = Request('file:///scrapy/sometempfile')
        assert self.mw.process_request(req6, self.spider) is None
        self.assertEqual(req6.headers.get('Cookie'), None)

    def test_local_domain(self):
        request = Request("http://example-host/", cookies={'currencyCookie': 'USD'})
        assert self.mw.process_request(request, self.spider) is None
        self.assertIn('Cookie', request.headers)
        self.assertEqual(b'currencyCookie=USD', request.headers['Cookie'])

    def _test_cookie_redirect(
        self,
        source,
        target,
        cookies1,
        cookies2,
    ):
        input_cookies = {'a': 'b'}

        if not isinstance(source, dict):
            source = {'url': source}
        if not isinstance(target, dict):
            target = {'url': target}
        target.setdefault('status', 301)

        source['cookies'] = input_cookies
        request1 = Request(**source)
        self.mw.process_request(request1, self.spider)
        cookies = request1.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies1 else None)

        target['headers'] = {
            'Location': target['url'],
        }
        response = Response(**target)
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

    def test_cookie_redirect_same_domain(self):
        self._test_cookie_redirect(
            'https://toscrape.com',
            'https://toscrape.com',
            cookies1=True,
            cookies2=True,
        )

    def test_cookie_redirect_same_domain_forcing_get(self):
        self._test_cookie_redirect(
            'https://toscrape.com',
            {'url': 'https://toscrape.com', 'status': 302},
            cookies1=True,
            cookies2=True,
        )

    def test_cookie_redirect_different_domain(self):
        self._test_cookie_redirect(
            'https://toscrape.com',
            'https://example.com',
            cookies1=True,
            cookies2=False,
        )

    def test_cookie_redirect_different_domain_forcing_get(self):
        self._test_cookie_redirect(
            'https://toscrape.com',
            {'url': 'https://example.com', 'status': 302},
            cookies1=True,
            cookies2=False,
        )

    def _test_cookie_header_redirect(
        self,
        source,
        target,
        cookies2,
    ):
        """Test the handling of a user-defined Cookie header when building a
        redirect follow-up request.

        We follow RFC 6265 for cookie handling. The Cookie header can only
        contain a list of key-value pairs (i.e. no additional cookie
        parameters like Domain or Path). Because of that, we follow the same
        rules that we would follow for the handling of the Set-Cookie response
        header when the Domain is not set: the cookies must be limited to the
        target URL domain (not even subdomains can receive those cookies).

        .. note:: This method tests the scenario where the cookie middleware is
                  disabled. Because of known issue #1992, when the cookies
                  middleware is enabled we do not need to be concerned about
                  the Cookie header getting leaked to unintended domains,
                  because the middleware empties the header from every request.
        """
        if not isinstance(source, dict):
            source = {'url': source}
        if not isinstance(target, dict):
            target = {'url': target}
        target.setdefault('status', 301)

        source['headers'] = {'Cookie': b'a=b'}
        request1 = Request(**source)

        target['headers'] = {
            'Location': target['url'],
        }
        response = Response(**target)

        request2 = self.redirect_middleware.process_response(
            request1,
            response,
            self.spider,
        )
        self.assertIsInstance(request2, Request)

        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies2 else None)

    def test_cookie_header_redirect_same_domain(self):
        self._test_cookie_header_redirect(
            'https://toscrape.com',
            'https://toscrape.com',
            cookies2=True,
        )

    def test_cookie_header_redirect_same_domain_forcing_get(self):
        self._test_cookie_header_redirect(
            'https://toscrape.com',
            {'url': 'https://toscrape.com', 'status': 302},
            cookies2=True,
        )

    def test_cookie_header_redirect_different_domain(self):
        self._test_cookie_header_redirect(
            'https://toscrape.com',
            'https://example.com',
            cookies2=False,
        )

    def test_cookie_header_redirect_different_domain_forcing_get(self):
        self._test_cookie_header_redirect(
            'https://toscrape.com',
            {'url': 'https://example.com', 'status': 302},
            cookies2=False,
        )

    def _test_user_set_cookie_domain_followup(
        self,
        url1,
        url2,
        domain,
        cookies1,
        cookies2,
    ):
        input_cookies = [
            {
                'name': 'a',
                'value': 'b',
                'domain': domain,
            }
        ]

        request1 = Request(url1, cookies=input_cookies)
        self.mw.process_request(request1, self.spider)
        cookies = request1.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies1 else None)

        request2 = Request(url2)
        self.mw.process_request(request2, self.spider)
        cookies = request2.headers.get('Cookie')
        self.assertEqual(cookies, b"a=b" if cookies2 else None)

    def test_user_set_cookie_domain_suffix_private(self):
        self._test_user_set_cookie_domain_followup(
            'https://books.toscrape.com',
            'https://quotes.toscrape.com',
            'toscrape.com',
            cookies1=True,
            cookies2=True,
        )

    def test_user_set_cookie_domain_suffix_public_period(self):
        self._test_user_set_cookie_domain_followup(
            'https://foo.co.uk',
            'https://bar.co.uk',
            'co.uk',
            cookies1=False,
            cookies2=False,
        )

    def test_user_set_cookie_domain_suffix_public_private(self):
        self._test_user_set_cookie_domain_followup(
            'https://foo.blogspot.com',
            'https://bar.blogspot.com',
            'blogspot.com',
            cookies1=False,
            cookies2=False,
        )

    def test_user_set_cookie_domain_public_period(self):
        self._test_user_set_cookie_domain_followup(
            'https://co.uk',
            'https://co.uk',
            'co.uk',
            cookies1=True,
            cookies2=True,
        )

    def _test_server_set_cookie_domain_followup(
        self,
        url1,
        url2,
        domain,
        cookies,
    ):
        request1 = Request(url1)
        self.mw.process_request(request1, self.spider)

        input_cookies = [
            {
                'name': 'a',
                'value': 'b',
                'domain': domain,
            }
        ]

        headers = {
            'Set-Cookie': _cookies_to_set_cookie_list(input_cookies),
        }
        response = Response(url1, status=200, headers=headers)
        self.assertEqual(
            self.mw.process_response(request1, response, self.spider),
            response,
        )

        request2 = Request(url2)
        self.mw.process_request(request2, self.spider)
        actual_cookies = request2.headers.get('Cookie')
        self.assertEqual(actual_cookies, b"a=b" if cookies else None)

    def test_server_set_cookie_domain_suffix_private(self):
        self._test_server_set_cookie_domain_followup(
            'https://books.toscrape.com',
            'https://quotes.toscrape.com',
            'toscrape.com',
            cookies=True,
        )

    def test_server_set_cookie_domain_suffix_public_period(self):
        self._test_server_set_cookie_domain_followup(
            'https://foo.co.uk',
            'https://bar.co.uk',
            'co.uk',
            cookies=False,
        )

    def test_server_set_cookie_domain_suffix_public_private(self):
        self._test_server_set_cookie_domain_followup(
            'https://foo.blogspot.com',
            'https://bar.blogspot.com',
            'blogspot.com',
            cookies=False,
        )

    def test_server_set_cookie_domain_public_period(self):
        self._test_server_set_cookie_domain_followup(
            'https://co.uk',
            'https://co.uk',
            'co.uk',
            cookies=True,
        )
