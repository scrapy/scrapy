import unittest
from unittest import mock
from warnings import catch_warnings

from w3lib.encoding import resolve_encoding

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import (Request, Response, TextResponse, HtmlResponse,
                         XmlResponse, Headers)
from scrapy.selector import Selector
from scrapy.utils.python import to_unicode
from scrapy.exceptions import NotSupported
from scrapy.link import Link
from tests import get_testdata


class BaseResponseTest(unittest.TestCase):

    response_class = Response

    def test_init(self):
        # Response requires url in the consturctor
        self.assertRaises(Exception, self.response_class)
        self.assertTrue(isinstance(self.response_class('http://example.com/'), self.response_class))
        self.assertRaises(TypeError, self.response_class, b"http://example.com")
        # body can be str or None
        self.assertTrue(isinstance(self.response_class('http://example.com/', body=b''), self.response_class))
        self.assertTrue(isinstance(self.response_class('http://example.com/', body=b'body'), self.response_class))
        # test presence of all optional parameters
        self.assertTrue(
            isinstance(
                self.response_class('http://example.com/', body=b'', headers={}, status=200), self.response_class
            )
        )

        r = self.response_class("http://www.example.com")
        assert isinstance(r.url, str)
        self.assertEqual(r.url, "http://www.example.com")
        self.assertEqual(r.status, 200)

        assert isinstance(r.headers, Headers)
        self.assertEqual(r.headers, {})

        headers = {"foo": "bar"}
        body = b"a body"
        r = self.response_class("http://www.example.com", headers=headers, body=body)

        assert r.headers is not headers
        self.assertEqual(r.headers[b"foo"], b"bar")

        r = self.response_class("http://www.example.com", status=301)
        self.assertEqual(r.status, 301)
        r = self.response_class("http://www.example.com", status='301')
        self.assertEqual(r.status, 301)
        self.assertRaises(ValueError, self.response_class, "http://example.com", status='lala200')

    def test_copy(self):
        """Test Response copy"""

        r1 = self.response_class("http://www.example.com", body=b"Some body")
        r1.flags.append('cached')
        r2 = r1.copy()

        self.assertEqual(r1.status, r2.status)
        self.assertEqual(r1.body, r2.body)

        # make sure flags list is shallow copied
        assert r1.flags is not r2.flags, "flags must be a shallow copy, not identical"
        self.assertEqual(r1.flags, r2.flags)

        # make sure headers attribute is shallow copied
        assert r1.headers is not r2.headers, "headers must be a shallow copy, not identical"
        self.assertEqual(r1.headers, r2.headers)

    def test_copy_meta(self):
        req = Request("http://www.example.com")
        req.meta['foo'] = 'bar'
        r1 = self.response_class("http://www.example.com", body=b"Some body", request=req)
        assert r1.meta is req.meta

    def test_copy_cb_kwargs(self):
        req = Request("http://www.example.com")
        req.cb_kwargs['foo'] = 'bar'
        r1 = self.response_class("http://www.example.com", body=b"Some body", request=req)
        assert r1.cb_kwargs is req.cb_kwargs

    def test_unavailable_meta(self):
        r1 = self.response_class("http://www.example.com", body=b"Some body")
        with self.assertRaisesRegex(AttributeError, r'Response\.meta not available'):
            r1.meta

    def test_unavailable_cb_kwargs(self):
        r1 = self.response_class("http://www.example.com", body=b"Some body")
        with self.assertRaisesRegex(AttributeError, r'Response\.cb_kwargs not available'):
            r1.cb_kwargs

    def test_copy_inherited_classes(self):
        """Test Response children copies preserve their class"""

        class CustomResponse(self.response_class):
            pass

        r1 = CustomResponse('http://www.example.com')
        r2 = r1.copy()

        assert type(r2) is CustomResponse

    def test_replace(self):
        """Test Response.replace() method"""
        hdrs = Headers({"key": "value"})
        r1 = self.response_class("http://www.example.com")
        r2 = r1.replace(status=301, body=b"New body", headers=hdrs)
        assert r1.body == b''
        self.assertEqual(r1.url, r2.url)
        self.assertEqual((r1.status, r2.status), (200, 301))
        self.assertEqual((r1.body, r2.body), (b'', b"New body"))
        self.assertEqual((r1.headers, r2.headers), ({}, hdrs))

        # Empty attributes (which may fail if not compared properly)
        r3 = self.response_class("http://www.example.com", flags=['cached'])
        r4 = r3.replace(body=b'', flags=[])
        self.assertEqual(r4.body, b'')
        self.assertEqual(r4.flags, [])

    def _assert_response_values(self, response, encoding, body):
        if isinstance(body, str):
            body_unicode = body
            body_bytes = body.encode(encoding)
        else:
            body_unicode = body.decode(encoding)
            body_bytes = body

        assert isinstance(response.body, bytes)
        assert isinstance(response.text, str)
        self._assert_response_encoding(response, encoding)
        self.assertEqual(response.body, body_bytes)
        self.assertEqual(response.body_as_unicode(), body_unicode)
        self.assertEqual(response.text, body_unicode)

    def _assert_response_encoding(self, response, encoding):
        self.assertEqual(response.encoding, resolve_encoding(encoding))

    def test_immutable_attributes(self):
        r = self.response_class("http://example.com")
        self.assertRaises(AttributeError, setattr, r, 'url', 'http://example2.com')
        self.assertRaises(AttributeError, setattr, r, 'body', 'xxx')

    def test_urljoin(self):
        """Test urljoin shortcut (only for existence, since behavior equals urljoin)"""
        joined = self.response_class('http://www.example.com').urljoin('/test')
        absolute = 'http://www.example.com/test'
        self.assertEqual(joined, absolute)

    def test_shortcut_attributes(self):
        r = self.response_class("http://example.com", body=b'hello')
        if self.response_class == Response:
            msg = "Response content isn't text"
            self.assertRaisesRegex(AttributeError, msg, getattr, r, 'text')
            self.assertRaisesRegex(NotSupported, msg, r.css, 'body')
            self.assertRaisesRegex(NotSupported, msg, r.xpath, '//body')
        else:
            r.text
            r.css('body')
            r.xpath('//body')

    # Response.follow

    def test_follow_url_absolute(self):
        self._assert_followed_url('http://foo.example.com',
                                  'http://foo.example.com')

    def test_follow_url_relative(self):
        self._assert_followed_url('foo',
                                  'http://example.com/foo')

    def test_follow_link(self):
        self._assert_followed_url(Link('http://example.com/foo'),
                                  'http://example.com/foo')

    def test_follow_None_url(self):
        r = self.response_class("http://example.com")
        self.assertRaises(ValueError, r.follow, None)

    def test_follow_whitespace_url(self):
        self._assert_followed_url('foo ',
                                  'http://example.com/foo%20')

    def test_follow_whitespace_link(self):
        self._assert_followed_url(Link('http://example.com/foo '),
                                  'http://example.com/foo%20')

    def test_follow_flags(self):
        res = self.response_class('http://example.com/')
        fol = res.follow('http://example.com/', flags=['cached', 'allowed'])
        self.assertEqual(fol.flags, ['cached', 'allowed'])

    # Response.follow_all

    def test_follow_all_absolute(self):
        url_list = ['http://example.org', 'http://www.example.org',
                    'http://example.com', 'http://www.example.com']
        self._assert_followed_all_urls(url_list, url_list)

    def test_follow_all_relative(self):
        relative = ['foo', 'bar', 'foo/bar', 'bar/foo']
        absolute = [
            'http://example.com/foo',
            'http://example.com/bar',
            'http://example.com/foo/bar',
            'http://example.com/bar/foo',
        ]
        self._assert_followed_all_urls(relative, absolute)

    def test_follow_all_links(self):
        absolute = [
            'http://example.com/foo',
            'http://example.com/bar',
            'http://example.com/foo/bar',
            'http://example.com/bar/foo',
        ]
        links = map(Link, absolute)
        self._assert_followed_all_urls(links, absolute)

    def test_follow_all_empty(self):
        r = self.response_class("http://example.com")
        self.assertEqual([], list(r.follow_all([])))

    def test_follow_all_invalid(self):
        r = self.response_class("http://example.com")
        if self.response_class == Response:
            with self.assertRaises(TypeError):
                list(r.follow_all(urls=None))
            with self.assertRaises(TypeError):
                list(r.follow_all(urls=12345))
            with self.assertRaises(ValueError):
                list(r.follow_all(urls=[None]))
        else:
            with self.assertRaises(ValueError):
                list(r.follow_all(urls=None))
            with self.assertRaises(TypeError):
                list(r.follow_all(urls=12345))
            with self.assertRaises(ValueError):
                list(r.follow_all(urls=[None]))

    def test_follow_all_whitespace(self):
        relative = ['foo ', 'bar ', 'foo/bar ', 'bar/foo ']
        absolute = [
            'http://example.com/foo%20',
            'http://example.com/bar%20',
            'http://example.com/foo/bar%20',
            'http://example.com/bar/foo%20',
        ]
        self._assert_followed_all_urls(relative, absolute)

    def test_follow_all_whitespace_links(self):
        absolute = [
            'http://example.com/foo ',
            'http://example.com/bar ',
            'http://example.com/foo/bar ',
            'http://example.com/bar/foo ',
        ]
        links = map(Link, absolute)
        expected = [u.replace(' ', '%20') for u in absolute]
        self._assert_followed_all_urls(links, expected)

    def test_follow_all_flags(self):
        re = self.response_class('http://www.example.com/')
        urls = [
            'http://www.example.com/',
            'http://www.example.com/2',
            'http://www.example.com/foo',
        ]
        fol = re.follow_all(urls, flags=['cached', 'allowed'])
        for req in fol:
            self.assertEqual(req.flags, ['cached', 'allowed'])

    def _assert_followed_url(self, follow_obj, target_url, response=None):
        if response is None:
            response = self._links_response()
        req = response.follow(follow_obj)
        self.assertEqual(req.url, target_url)
        return req

    def _assert_followed_all_urls(self, follow_obj, target_urls, response=None):
        if response is None:
            response = self._links_response()
        followed = response.follow_all(follow_obj)
        for req, target in zip(followed, target_urls):
            self.assertEqual(req.url, target)
            yield req

    def _links_response(self):
        body = get_testdata('link_extractor', 'linkextractor.html')
        resp = self.response_class('http://example.com/index', body=body)
        return resp

    def _links_response_no_href(self):
        body = get_testdata('link_extractor', 'linkextractor_no_href.html')
        resp = self.response_class('http://example.com/index', body=body)
        return resp


class TextResponseTest(BaseResponseTest):

    response_class = TextResponse

    def test_replace(self):
        super().test_replace()
        r1 = self.response_class("http://www.example.com", body="hello", encoding="cp852")
        r2 = r1.replace(url="http://www.example.com/other")
        r3 = r1.replace(url="http://www.example.com/other", encoding="latin1")

        assert isinstance(r2, self.response_class)
        self.assertEqual(r2.url, "http://www.example.com/other")
        self._assert_response_encoding(r2, "cp852")
        self.assertEqual(r3.url, "http://www.example.com/other")
        self.assertEqual(r3._declared_encoding(), "latin1")

    def test_unicode_url(self):
        # instantiate with unicode url without encoding (should set default encoding)
        resp = self.response_class("http://www.example.com/")
        self._assert_response_encoding(resp, self.response_class._DEFAULT_ENCODING)

        # make sure urls are converted to str
        resp = self.response_class(url="http://www.example.com/", encoding='utf-8')
        assert isinstance(resp.url, str)

        resp = self.response_class(url="http://www.example.com/price/\xa3", encoding='utf-8')
        self.assertEqual(resp.url, to_unicode(b'http://www.example.com/price/\xc2\xa3'))
        resp = self.response_class(url="http://www.example.com/price/\xa3", encoding='latin-1')
        self.assertEqual(resp.url, 'http://www.example.com/price/\xa3')
        resp = self.response_class("http://www.example.com/price/\xa3",
                                   headers={"Content-type": ["text/html; charset=utf-8"]})
        self.assertEqual(resp.url, to_unicode(b'http://www.example.com/price/\xc2\xa3'))
        resp = self.response_class("http://www.example.com/price/\xa3",
                                   headers={"Content-type": ["text/html; charset=iso-8859-1"]})
        self.assertEqual(resp.url, 'http://www.example.com/price/\xa3')

    def test_unicode_body(self):
        unicode_string = ('\u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0447\u0435\u0441\u043a\u0438\u0439 '
                          '\u0442\u0435\u043a\u0441\u0442')
        self.assertRaises(TypeError, self.response_class, 'http://www.example.com', body='unicode body')

        original_string = unicode_string.encode('cp1251')
        r1 = self.response_class('http://www.example.com', body=original_string, encoding='cp1251')

        # check body_as_unicode
        self.assertTrue(isinstance(r1.body_as_unicode(), str))
        self.assertEqual(r1.body_as_unicode(), unicode_string)

        # check response.text
        self.assertTrue(isinstance(r1.text, str))
        self.assertEqual(r1.text, unicode_string)

    def test_encoding(self):
        r1 = self.response_class("http://www.example.com", body=b"\xc2\xa3",
                                 headers={"Content-type": ["text/html; charset=utf-8"]})
        r2 = self.response_class("http://www.example.com", encoding='utf-8', body="\xa3")
        r3 = self.response_class("http://www.example.com", body=b"\xa3",
                                 headers={"Content-type": ["text/html; charset=iso-8859-1"]})
        r4 = self.response_class("http://www.example.com", body=b"\xa2\xa3")
        r5 = self.response_class("http://www.example.com", body=b"\xc2\xa3",
                                 headers={"Content-type": ["text/html; charset=None"]})
        r6 = self.response_class("http://www.example.com", body=b"\xa8D",
                                 headers={"Content-type": ["text/html; charset=gb2312"]})
        r7 = self.response_class("http://www.example.com", body=b"\xa8D",
                                 headers={"Content-type": ["text/html; charset=gbk"]})

        self.assertEqual(r1._headers_encoding(), "utf-8")
        self.assertEqual(r2._headers_encoding(), None)
        self.assertEqual(r2._declared_encoding(), 'utf-8')
        self._assert_response_encoding(r2, 'utf-8')
        self.assertEqual(r3._headers_encoding(), "cp1252")
        self.assertEqual(r3._declared_encoding(), "cp1252")
        self.assertEqual(r4._headers_encoding(), None)
        self.assertEqual(r5._headers_encoding(), None)
        self._assert_response_encoding(r5, "utf-8")
        assert r4._body_inferred_encoding() is not None and r4._body_inferred_encoding() != 'ascii'
        self._assert_response_values(r1, 'utf-8', "\xa3")
        self._assert_response_values(r2, 'utf-8', "\xa3")
        self._assert_response_values(r3, 'iso-8859-1', "\xa3")
        self._assert_response_values(r6, 'gb18030', "\u2015")
        self._assert_response_values(r7, 'gb18030', "\u2015")

        # TextResponse (and subclasses) must be passed a encoding when instantiating with unicode bodies
        self.assertRaises(TypeError, self.response_class, "http://www.example.com", body="\xa3")

    def test_declared_encoding_invalid(self):
        """Check that unknown declared encodings are ignored"""
        r = self.response_class("http://www.example.com",
                                headers={"Content-type": ["text/html; charset=UKNOWN"]},
                                body=b"\xc2\xa3")
        self.assertEqual(r._declared_encoding(), None)
        self._assert_response_values(r, 'utf-8', "\xa3")

    def test_utf16(self):
        """Test utf-16 because UnicodeDammit is known to have problems with"""
        r = self.response_class("http://www.example.com",
                                body=b'\xff\xfeh\x00i\x00',
                                encoding='utf-16')
        self._assert_response_values(r, 'utf-16', "hi")

    def test_invalid_utf8_encoded_body_with_valid_utf8_BOM(self):
        r6 = self.response_class("http://www.example.com",
                                 headers={"Content-type": ["text/html; charset=utf-8"]},
                                 body=b"\xef\xbb\xbfWORD\xe3\xab")
        self.assertEqual(r6.encoding, 'utf-8')
        self.assertIn(r6.text, {
            'WORD\ufffd\ufffd',  # w3lib < 1.19.0
            'WORD\ufffd',        # w3lib >= 1.19.0
        })

    def test_bom_is_removed_from_body(self):
        # Inferring encoding from body also cache decoded body as sideeffect,
        # this test tries to ensure that calling response.encoding and
        # response.text in indistint order doesn't affect final
        # values for encoding and decoded body.
        url = 'http://example.com'
        body = b"\xef\xbb\xbfWORD"
        headers = {"Content-type": ["text/html; charset=utf-8"]}

        # Test response without content-type and BOM encoding
        response = self.response_class(url, body=body)
        self.assertEqual(response.encoding, 'utf-8')
        self.assertEqual(response.text, 'WORD')
        response = self.response_class(url, body=body)
        self.assertEqual(response.text, 'WORD')
        self.assertEqual(response.encoding, 'utf-8')

        # Body caching sideeffect isn't triggered when encoding is declared in
        # content-type header but BOM still need to be removed from decoded
        # body
        response = self.response_class(url, headers=headers, body=body)
        self.assertEqual(response.encoding, 'utf-8')
        self.assertEqual(response.text, 'WORD')
        response = self.response_class(url, headers=headers, body=body)
        self.assertEqual(response.text, 'WORD')
        self.assertEqual(response.encoding, 'utf-8')

    def test_replace_wrong_encoding(self):
        """Test invalid chars are replaced properly"""
        r = self.response_class("http://www.example.com", encoding='utf-8', body=b'PREFIX\xe3\xabSUFFIX')
        # XXX: Policy for replacing invalid chars may suffer minor variations
        # but it should always contain the unicode replacement char ('\ufffd')
        assert '\ufffd' in r.text, repr(r.text)
        assert 'PREFIX' in r.text, repr(r.text)
        assert 'SUFFIX' in r.text, repr(r.text)

        # Do not destroy html tags due to encoding bugs
        r = self.response_class("http://example.com", encoding='utf-8',
                                body=b'\xf0<span>value</span>')
        assert '<span>value</span>' in r.text, repr(r.text)

        # FIXME: This test should pass once we stop using BeautifulSoup's UnicodeDammit in TextResponse
        # r = self.response_class("http://www.example.com", body=b'PREFIX\xe3\xabSUFFIX')
        # assert '\ufffd' in r.text, repr(r.text)

    def test_selector(self):
        body = b"<html><head><title>Some page</title><body></body></html>"
        response = self.response_class("http://www.example.com", body=body)

        self.assertIsInstance(response.selector, Selector)
        self.assertEqual(response.selector.type, 'html')
        self.assertIs(response.selector, response.selector)  # property is cached
        self.assertIs(response.selector.response, response)

        self.assertEqual(
            response.selector.xpath("//title/text()").getall(),
            ['Some page']
        )
        self.assertEqual(
            response.selector.css("title::text").getall(),
            ['Some page']
        )
        self.assertEqual(
            response.selector.re("Some (.*)</title>"),
            ['page']
        )

    def test_selector_shortcuts(self):
        body = b"<html><head><title>Some page</title><body></body></html>"
        response = self.response_class("http://www.example.com", body=body)

        self.assertEqual(
            response.xpath("//title/text()").getall(),
            response.selector.xpath("//title/text()").getall(),
        )
        self.assertEqual(
            response.css("title::text").getall(),
            response.selector.css("title::text").getall(),
        )

    def test_selector_shortcuts_kwargs(self):
        body = b"<html><head><title>Some page</title><body><p class=\"content\">A nice paragraph.</p></body></html>"
        response = self.response_class("http://www.example.com", body=body)

        self.assertEqual(
            response.xpath("normalize-space(//p[@class=$pclass])", pclass="content").getall(),
            response.xpath("normalize-space(//p[@class=\"content\"])").getall(),
        )
        self.assertEqual(
            response.xpath(
                "//title[count(following::p[@class=$pclass])=$pcount]/text()",
                pclass="content", pcount=1,
            ).getall(),
            response.xpath("//title[count(following::p[@class=\"content\"])=1]/text()").getall(),
        )

    def test_urljoin_with_base_url(self):
        """Test urljoin shortcut which also evaluates base-url through get_base_url()."""
        body = b'<html><body><base href="https://example.net"></body></html>'
        joined = self.response_class('http://www.example.com', body=body).urljoin('/test')
        absolute = 'https://example.net/test'
        self.assertEqual(joined, absolute)

        body = b'<html><body><base href="/elsewhere"></body></html>'
        joined = self.response_class('http://www.example.com', body=body).urljoin('test')
        absolute = 'http://www.example.com/test'
        self.assertEqual(joined, absolute)

        body = b'<html><body><base href="/elsewhere/"></body></html>'
        joined = self.response_class('http://www.example.com', body=body).urljoin('test')
        absolute = 'http://www.example.com/elsewhere/test'
        self.assertEqual(joined, absolute)

    def test_follow_selector(self):
        resp = self._links_response()
        urls = [
            'http://example.com/sample2.html',
            'http://example.com/sample3.html',
            'http://example.com/sample3.html',
            'http://example.com/sample3.html#foo',
            'http://www.google.com/something',
            'http://example.com/innertag.html'
        ]

        # select <a> elements
        for sellist in [resp.css('a'), resp.xpath('//a')]:
            for sel, url in zip(sellist, urls):
                self._assert_followed_url(sel, url, response=resp)

        # select <link> elements
        self._assert_followed_url(
            Selector(text='<link href="foo"></link>').css('link')[0],
            'http://example.com/foo',
            response=resp
        )

        # href attributes should work
        for sellist in [resp.css('a::attr(href)'), resp.xpath('//a/@href')]:
            for sel, url in zip(sellist, urls):
                self._assert_followed_url(sel, url, response=resp)

        # non-a elements are not supported
        self.assertRaises(ValueError, resp.follow, resp.css('div')[0])

    def test_follow_selector_list(self):
        resp = self._links_response()
        self.assertRaisesRegex(ValueError, 'SelectorList',
                               resp.follow, resp.css('a'))

    def test_follow_selector_invalid(self):
        resp = self._links_response()
        self.assertRaisesRegex(ValueError, 'Unsupported',
                               resp.follow, resp.xpath('count(//div)')[0])

    def test_follow_selector_attribute(self):
        resp = self._links_response()
        for src in resp.css('img::attr(src)'):
            self._assert_followed_url(src, 'http://example.com/sample2.jpg')

    def test_follow_selector_no_href(self):
        resp = self.response_class(
            url='http://example.com',
            body=b'<html><body><a name=123>click me</a></body></html>',
        )
        self.assertRaisesRegex(ValueError, 'no href',
                               resp.follow, resp.css('a')[0])

    def test_follow_whitespace_selector(self):
        resp = self.response_class(
            'http://example.com',
            body=b'''<html><body><a href=" foo\n">click me</a></body></html>'''
        )
        self._assert_followed_url(
            resp.css('a')[0],
            'http://example.com/foo',
            response=resp)
        self._assert_followed_url(
            resp.css('a::attr(href)')[0],
            'http://example.com/foo',
            response=resp)

    def test_follow_encoding(self):
        resp1 = self.response_class(
            'http://example.com',
            encoding='utf8',
            body='<html><body><a href="foo?привет">click me</a></body></html>'.encode('utf8')
        )
        req = self._assert_followed_url(
            resp1.css('a')[0],
            'http://example.com/foo?%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82',
            response=resp1,
        )
        self.assertEqual(req.encoding, 'utf8')

        resp2 = self.response_class(
            'http://example.com',
            encoding='cp1251',
            body='<html><body><a href="foo?привет">click me</a></body></html>'.encode('cp1251')
        )
        req = self._assert_followed_url(
            resp2.css('a')[0],
            'http://example.com/foo?%EF%F0%E8%E2%E5%F2',
            response=resp2,
        )
        self.assertEqual(req.encoding, 'cp1251')

    def test_follow_flags(self):
        res = self.response_class('http://example.com/')
        fol = res.follow('http://example.com/', flags=['cached', 'allowed'])
        self.assertEqual(fol.flags, ['cached', 'allowed'])

    def test_follow_all_flags(self):
        re = self.response_class('http://www.example.com/')
        urls = [
            'http://www.example.com/',
            'http://www.example.com/2',
            'http://www.example.com/foo',
        ]
        fol = re.follow_all(urls, flags=['cached', 'allowed'])
        for req in fol:
            self.assertEqual(req.flags, ['cached', 'allowed'])

    def test_follow_all_css(self):
        expected = [
            'http://example.com/sample3.html',
            'http://example.com/innertag.html',
        ]
        response = self._links_response()
        extracted = [r.url for r in response.follow_all(css='a[href*="example.com"]')]
        self.assertEqual(expected, extracted)

    def test_follow_all_css_skip_invalid(self):
        expected = [
            'http://example.com/page/1/',
            'http://example.com/page/3/',
            'http://example.com/page/4/',
        ]
        response = self._links_response_no_href()
        extracted1 = [r.url for r in response.follow_all(css='.pagination a')]
        self.assertEqual(expected, extracted1)
        extracted2 = [r.url for r in response.follow_all(response.css('.pagination a'))]
        self.assertEqual(expected, extracted2)

    def test_follow_all_xpath(self):
        expected = [
            'http://example.com/sample3.html',
            'http://example.com/innertag.html',
        ]
        response = self._links_response()
        extracted = response.follow_all(xpath='//a[contains(@href, "example.com")]')
        self.assertEqual(expected, [r.url for r in extracted])

    def test_follow_all_xpath_skip_invalid(self):
        expected = [
            'http://example.com/page/1/',
            'http://example.com/page/3/',
            'http://example.com/page/4/',
        ]
        response = self._links_response_no_href()
        extracted1 = [r.url for r in response.follow_all(xpath='//div[@id="pagination"]/a')]
        self.assertEqual(expected, extracted1)
        extracted2 = [r.url for r in response.follow_all(response.xpath('//div[@id="pagination"]/a'))]
        self.assertEqual(expected, extracted2)

    def test_follow_all_too_many_arguments(self):
        response = self._links_response()
        with self.assertRaises(ValueError):
            response.follow_all(css='a[href*="example.com"]', xpath='//a[contains(@href, "example.com")]')

    def test_body_as_unicode_deprecation_warning(self):
        with catch_warnings(record=True) as warnings:
            r1 = self.response_class("http://www.example.com", body='Hello', encoding='utf-8')
            self.assertEqual(r1.body_as_unicode(), 'Hello')
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, ScrapyDeprecationWarning)

    def test_json_response(self):
        json_body = b"""{"ip": "109.187.217.200"}"""
        json_response = self.response_class("http://www.example.com", body=json_body)
        self.assertEqual(json_response.json(), {'ip': '109.187.217.200'})

        text_body = b"""<html><body>text</body></html>"""
        text_response = self.response_class("http://www.example.com", body=text_body)
        with self.assertRaises(ValueError):
            text_response.json()

    def test_cache_json_response(self):
        json_valid_bodies = [b"""{"ip": "109.187.217.200"}""", b"""null"""]
        for json_body in json_valid_bodies:
            json_response = self.response_class("http://www.example.com", body=json_body)

            with mock.patch('json.loads') as mock_json:
                for _ in range(2):
                    json_response.json()
                mock_json.assert_called_once_with(json_body.decode())


class HtmlResponseTest(TextResponseTest):

    response_class = HtmlResponse

    def test_html_encoding(self):

        body = b"""<html><head><title>Some page</title><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
        </head><body>Price: \xa3100</body></html>'
        """
        r1 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r1, 'iso-8859-1', body)

        body = b"""<?xml version="1.0" encoding="iso-8859-1"?>
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
        Price: \xa3100
        """
        r2 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r2, 'iso-8859-1', body)

        # for conflicting declarations headers must take precedence
        body = b"""<html><head><title>Some page</title><meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        </head><body>Price: \xa3100</body></html>'
        """
        r3 = self.response_class("http://www.example.com", body=body,
                                 headers={"Content-type": ["text/html; charset=iso-8859-1"]})
        self._assert_response_values(r3, 'iso-8859-1', body)

        # make sure replace() preserves the encoding of the original response
        body = b"New body \xa3"
        r4 = r3.replace(body=body)
        self._assert_response_values(r4, 'iso-8859-1', body)

    def test_html5_meta_charset(self):
        body = b"""<html><head><meta charset="gb2312" /><title>Some page</title><body>bla bla</body>"""
        r1 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r1, 'gb2312', body)


class XmlResponseTest(TextResponseTest):

    response_class = XmlResponse

    def test_xml_encoding(self):
        body = b"<xml></xml>"
        r1 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r1, self.response_class._DEFAULT_ENCODING, body)

        body = b"""<?xml version="1.0" encoding="iso-8859-1"?><xml></xml>"""
        r2 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r2, 'iso-8859-1', body)

        # make sure replace() preserves the explicit encoding passed in the __init__ method
        body = b"""<?xml version="1.0" encoding="iso-8859-1"?><xml></xml>"""
        r3 = self.response_class("http://www.example.com", body=body, encoding='utf-8')
        body2 = b"New body"
        r4 = r3.replace(body=body2)
        self._assert_response_values(r4, 'utf-8', body2)

    def test_replace_encoding(self):
        # make sure replace() keeps the previous encoding unless overridden explicitly
        body = b"""<?xml version="1.0" encoding="iso-8859-1"?><xml></xml>"""
        body2 = b"""<?xml version="1.0" encoding="utf-8"?><xml></xml>"""
        r5 = self.response_class("http://www.example.com", body=body)
        r6 = r5.replace(body=body2)
        r7 = r5.replace(body=body2, encoding='utf-8')
        self._assert_response_values(r5, 'iso-8859-1', body)
        self._assert_response_values(r6, 'iso-8859-1', body2)
        self._assert_response_values(r7, 'utf-8', body2)

    def test_selector(self):
        body = b'<?xml version="1.0" encoding="utf-8"?><xml><elem>value</elem></xml>'
        response = self.response_class("http://www.example.com", body=body)

        self.assertIsInstance(response.selector, Selector)
        self.assertEqual(response.selector.type, 'xml')
        self.assertIs(response.selector, response.selector)  # property is cached
        self.assertIs(response.selector.response, response)

        self.assertEqual(
            response.selector.xpath("//elem/text()").getall(),
            ['value']
        )

    def test_selector_shortcuts(self):
        body = b'<?xml version="1.0" encoding="utf-8"?><xml><elem>value</elem></xml>'
        response = self.response_class("http://www.example.com", body=body)

        self.assertEqual(
            response.xpath("//elem/text()").getall(),
            response.selector.xpath("//elem/text()").getall(),
        )

    def test_selector_shortcuts_kwargs(self):
        body = b'''<?xml version="1.0" encoding="utf-8"?>
        <xml xmlns:somens="http://scrapy.org">
        <somens:elem>value</somens:elem>
        </xml>'''
        response = self.response_class("http://www.example.com", body=body)

        self.assertEqual(
            response.xpath("//s:elem/text()", namespaces={'s': 'http://scrapy.org'}).getall(),
            response.selector.xpath("//s:elem/text()", namespaces={'s': 'http://scrapy.org'}).getall(),
        )

        response.selector.register_namespace('s2', 'http://scrapy.org')
        self.assertEqual(
            response.xpath("//s1:elem/text()", namespaces={'s1': 'http://scrapy.org'}).getall(),
            response.selector.xpath("//s2:elem/text()").getall(),
        )
