# -*- coding: utf-8 -*-
import unittest

import six
from six.moves.urllib.parse import urlparse

from scrapy.spiders import Spider
from scrapy.utils.url import (url_is_from_any_domain, url_is_from_spider,
                              canonicalize_url, add_http_if_no_scheme,
                              guess_scheme, parse_url)

__doctests__ = ['scrapy.utils.url']


class UrlUtilsTest(unittest.TestCase):

    def test_url_is_from_any_domain(self):
        url = 'http://www.wheele-bin-art.co.uk/get/product/123'
        self.assertTrue(url_is_from_any_domain(url, ['wheele-bin-art.co.uk']))
        self.assertFalse(url_is_from_any_domain(url, ['art.co.uk']))

        url = 'http://wheele-bin-art.co.uk/get/product/123'
        self.assertTrue(url_is_from_any_domain(url, ['wheele-bin-art.co.uk']))
        self.assertFalse(url_is_from_any_domain(url, ['art.co.uk']))

        url = 'http://www.Wheele-Bin-Art.co.uk/get/product/123'
        self.assertTrue(url_is_from_any_domain(url, ['wheele-bin-art.CO.UK']))
        self.assertTrue(url_is_from_any_domain(url, ['WHEELE-BIN-ART.CO.UK']))

        url = 'http://192.169.0.15:8080/mypage.html'
        self.assertTrue(url_is_from_any_domain(url, ['192.169.0.15:8080']))
        self.assertFalse(url_is_from_any_domain(url, ['192.169.0.15']))

        url = 'javascript:%20document.orderform_2581_1190810811.mode.value=%27add%27;%20javascript:%20document.orderform_2581_1190810811.submit%28%29'
        self.assertFalse(url_is_from_any_domain(url, ['testdomain.com']))
        self.assertFalse(url_is_from_any_domain(url+'.testdomain.com', ['testdomain.com']))

    def test_url_is_from_spider(self):
        spider = Spider(name='example.com')
        self.assertTrue(url_is_from_spider('http://www.example.com/some/page.html', spider))
        self.assertTrue(url_is_from_spider('http://sub.example.com/some/page.html', spider))
        self.assertFalse(url_is_from_spider('http://www.example.org/some/page.html', spider))
        self.assertFalse(url_is_from_spider('http://www.example.net/some/page.html', spider))

    def test_url_is_from_spider_class_attributes(self):
        class MySpider(Spider):
            name = 'example.com'
        self.assertTrue(url_is_from_spider('http://www.example.com/some/page.html', MySpider))
        self.assertTrue(url_is_from_spider('http://sub.example.com/some/page.html', MySpider))
        self.assertFalse(url_is_from_spider('http://www.example.org/some/page.html', MySpider))
        self.assertFalse(url_is_from_spider('http://www.example.net/some/page.html', MySpider))

    def test_url_is_from_spider_with_allowed_domains(self):
        spider = Spider(name='example.com', allowed_domains=['example.org', 'example.net'])
        self.assertTrue(url_is_from_spider('http://www.example.com/some/page.html', spider))
        self.assertTrue(url_is_from_spider('http://sub.example.com/some/page.html', spider))
        self.assertTrue(url_is_from_spider('http://example.com/some/page.html', spider))
        self.assertTrue(url_is_from_spider('http://www.example.org/some/page.html', spider))
        self.assertTrue(url_is_from_spider('http://www.example.net/some/page.html', spider))
        self.assertFalse(url_is_from_spider('http://www.example.us/some/page.html', spider))

        spider = Spider(name='example.com', allowed_domains=set(('example.com', 'example.net')))
        self.assertTrue(url_is_from_spider('http://www.example.com/some/page.html', spider))

        spider = Spider(name='example.com', allowed_domains=('example.com', 'example.net'))
        self.assertTrue(url_is_from_spider('http://www.example.com/some/page.html', spider))

    def test_url_is_from_spider_with_allowed_domains_class_attributes(self):
        class MySpider(Spider):
            name = 'example.com'
            allowed_domains = ('example.org', 'example.net')
        self.assertTrue(url_is_from_spider('http://www.example.com/some/page.html', MySpider))
        self.assertTrue(url_is_from_spider('http://sub.example.com/some/page.html', MySpider))
        self.assertTrue(url_is_from_spider('http://example.com/some/page.html', MySpider))
        self.assertTrue(url_is_from_spider('http://www.example.org/some/page.html', MySpider))
        self.assertTrue(url_is_from_spider('http://www.example.net/some/page.html', MySpider))
        self.assertFalse(url_is_from_spider('http://www.example.us/some/page.html', MySpider))


class CanonicalizeUrlTest(unittest.TestCase):

    def test_canonicalize_url(self):
        # simplest case
        self.assertEqual(canonicalize_url("http://www.example.com/"),
                                          "http://www.example.com/")

    def test_return_str(self):
        assert isinstance(canonicalize_url(u"http://www.example.com"), str)
        assert isinstance(canonicalize_url(b"http://www.example.com"), str)

    def test_append_missing_path(self):
        self.assertEqual(canonicalize_url("http://www.example.com"),
                                          "http://www.example.com/")

    def test_typical_usage(self):
        self.assertEqual(canonicalize_url("http://www.example.com/do?a=1&b=2&c=3"),
                                          "http://www.example.com/do?a=1&b=2&c=3")
        self.assertEqual(canonicalize_url("http://www.example.com/do?c=1&b=2&a=3"),
                                          "http://www.example.com/do?a=3&b=2&c=1")
        self.assertEqual(canonicalize_url("http://www.example.com/do?&a=1"),
                                          "http://www.example.com/do?a=1")

    def test_sorting(self):
        self.assertEqual(canonicalize_url("http://www.example.com/do?c=3&b=5&b=2&a=50"),
                                          "http://www.example.com/do?a=50&b=2&b=5&c=3")

    def test_keep_blank_values(self):
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&a=2", keep_blank_values=False),
                                          "http://www.example.com/do?a=2")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&a=2"),
                                          "http://www.example.com/do?a=2&b=")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&c&a=2", keep_blank_values=False),
                                          "http://www.example.com/do?a=2")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&c&a=2"),
                                          "http://www.example.com/do?a=2&b=&c=")

        self.assertEqual(canonicalize_url(u'http://www.example.com/do?1750,4'),
                                           'http://www.example.com/do?1750%2C4=')

    def test_spaces(self):
        self.assertEqual(canonicalize_url("http://www.example.com/do?q=a space&a=1"),
                                          "http://www.example.com/do?a=1&q=a+space")
        self.assertEqual(canonicalize_url("http://www.example.com/do?q=a+space&a=1"),
                                          "http://www.example.com/do?a=1&q=a+space")
        self.assertEqual(canonicalize_url("http://www.example.com/do?q=a%20space&a=1"),
                                          "http://www.example.com/do?a=1&q=a+space")

    def test_canonicalize_url_unicode_path(self):
        self.assertEqual(canonicalize_url(u"http://www.example.com/résumé"),
                                          "http://www.example.com/r%C3%A9sum%C3%A9")

    def test_canonicalize_url_unicode_query_string(self):
        # default encoding for path and query is UTF-8
        self.assertEqual(canonicalize_url(u"http://www.example.com/résumé?q=résumé"),
                                          "http://www.example.com/r%C3%A9sum%C3%A9?q=r%C3%A9sum%C3%A9")

        # passed encoding will affect query string
        self.assertEqual(canonicalize_url(u"http://www.example.com/résumé?q=résumé", encoding='latin1'),
                                          "http://www.example.com/r%C3%A9sum%C3%A9?q=r%E9sum%E9")

        self.assertEqual(canonicalize_url(u"http://www.example.com/résumé?country=Россия", encoding='cp1251'),
                                          "http://www.example.com/r%C3%A9sum%C3%A9?country=%D0%EE%F1%F1%E8%FF")

    def test_canonicalize_url_unicode_query_string_wrong_encoding(self):
        # trying to encode with wrong encoding
        # fallback to UTF-8
        self.assertEqual(canonicalize_url(u"http://www.example.com/résumé?currency=€", encoding='latin1'),
                                          "http://www.example.com/r%C3%A9sum%C3%A9?currency=%E2%82%AC")

        self.assertEqual(canonicalize_url(u"http://www.example.com/résumé?country=Россия", encoding='latin1'),
                                          "http://www.example.com/r%C3%A9sum%C3%A9?country=%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D1%8F")

    def test_normalize_percent_encoding_in_paths(self):
        self.assertEqual(canonicalize_url("http://www.example.com/r%c3%a9sum%c3%a9"),
                                          "http://www.example.com/r%C3%A9sum%C3%A9")

        # non-UTF8 encoded sequences: they should be kept untouched, only upper-cased
        # 'latin1'-encoded sequence in path
        self.assertEqual(canonicalize_url("http://www.example.com/a%a3do"),
                                          "http://www.example.com/a%A3do")

        # 'latin1'-encoded path, UTF-8 encoded query string
        self.assertEqual(canonicalize_url("http://www.example.com/a%a3do?q=r%c3%a9sum%c3%a9"),
                                          "http://www.example.com/a%A3do?q=r%C3%A9sum%C3%A9")

        # 'latin1'-encoded path and query string
        self.assertEqual(canonicalize_url("http://www.example.com/a%a3do?q=r%e9sum%e9"),
                                          "http://www.example.com/a%A3do?q=r%E9sum%E9")

    def test_normalize_percent_encoding_in_query_arguments(self):
        self.assertEqual(canonicalize_url("http://www.example.com/do?k=b%a3"),
                                          "http://www.example.com/do?k=b%A3")

        self.assertEqual(canonicalize_url("http://www.example.com/do?k=r%c3%a9sum%c3%a9"),
                                          "http://www.example.com/do?k=r%C3%A9sum%C3%A9")

    def test_non_ascii_percent_encoding_in_paths(self):
        self.assertEqual(canonicalize_url("http://www.example.com/a do?a=1"),
                                          "http://www.example.com/a%20do?a=1"),
        self.assertEqual(canonicalize_url("http://www.example.com/a %20do?a=1"),
                                          "http://www.example.com/a%20%20do?a=1"),
        self.assertEqual(canonicalize_url(u"http://www.example.com/a do£.html?a=1"),
                                          "http://www.example.com/a%20do%C2%A3.html?a=1")
        self.assertEqual(canonicalize_url(b"http://www.example.com/a do\xc2\xa3.html?a=1"),
                                          "http://www.example.com/a%20do%C2%A3.html?a=1")

    def test_non_ascii_percent_encoding_in_query_arguments(self):
        self.assertEqual(canonicalize_url(u"http://www.example.com/do?price=£500&a=5&z=3"),
                                          u"http://www.example.com/do?a=5&price=%C2%A3500&z=3")
        self.assertEqual(canonicalize_url(b"http://www.example.com/do?price=\xc2\xa3500&a=5&z=3"),
                                          "http://www.example.com/do?a=5&price=%C2%A3500&z=3")
        self.assertEqual(canonicalize_url(b"http://www.example.com/do?price(\xc2\xa3)=500&a=1"),
                                          "http://www.example.com/do?a=1&price%28%C2%A3%29=500")

    def test_urls_with_auth_and_ports(self):
        self.assertEqual(canonicalize_url(u"http://user:pass@www.example.com:81/do?now=1"),
                                          u"http://user:pass@www.example.com:81/do?now=1")

    def test_remove_fragments(self):
        self.assertEqual(canonicalize_url(u"http://user:pass@www.example.com/do?a=1#frag"),
                                          u"http://user:pass@www.example.com/do?a=1")
        self.assertEqual(canonicalize_url(u"http://user:pass@www.example.com/do?a=1#frag", keep_fragments=True),
                                          u"http://user:pass@www.example.com/do?a=1#frag")

    def test_dont_convert_safe_characters(self):
        # dont convert safe characters to percent encoding representation
        self.assertEqual(canonicalize_url(
            "http://www.simplybedrooms.com/White-Bedroom-Furniture/Bedroom-Mirror:-Josephine-Cheval-Mirror.html"),
            "http://www.simplybedrooms.com/White-Bedroom-Furniture/Bedroom-Mirror:-Josephine-Cheval-Mirror.html")

    def test_safe_characters_unicode(self):
        # urllib.quote uses a mapping cache of encoded characters. when parsing
        # an already percent-encoded url, it will fail if that url was not
        # percent-encoded as utf-8, that's why canonicalize_url must always
        # convert the urls to string. the following test asserts that
        # functionality.
        self.assertEqual(canonicalize_url(u'http://www.example.com/caf%E9-con-leche.htm'),
                                           'http://www.example.com/caf%E9-con-leche.htm')

    def test_domains_are_case_insensitive(self):
        self.assertEqual(canonicalize_url("http://www.EXAMPLE.com/"),
                                          "http://www.example.com/")

    def test_canonicalize_idns(self):
        self.assertEqual(canonicalize_url(u'http://www.bücher.de?q=bücher'),
                                           'http://www.xn--bcher-kva.de/?q=b%C3%BCcher')
        # Japanese (+ reordering query parameters)
        self.assertEqual(canonicalize_url(u'http://はじめよう.みんな/?query=サ&maxResults=5'),
                                           'http://xn--p8j9a0d9c9a.xn--q9jyb4c/?maxResults=5&query=%E3%82%B5')

    def test_quoted_slash_and_question_sign(self):
        self.assertEqual(canonicalize_url("http://foo.com/AC%2FDC+rocks%3f/?yeah=1"),
                         "http://foo.com/AC%2FDC+rocks%3F/?yeah=1")
        self.assertEqual(canonicalize_url("http://foo.com/AC%2FDC/"),
                         "http://foo.com/AC%2FDC/")

    def test_canonicalize_urlparsed(self):
        # canonicalize_url() can be passed an already urlparse'd URL
        self.assertEqual(canonicalize_url(urlparse(u"http://www.example.com/résumé?q=résumé")),
                                          "http://www.example.com/r%C3%A9sum%C3%A9?q=r%C3%A9sum%C3%A9")
        self.assertEqual(canonicalize_url(urlparse('http://www.example.com/caf%e9-con-leche.htm')),
                                          'http://www.example.com/caf%E9-con-leche.htm')
        self.assertEqual(canonicalize_url(urlparse("http://www.example.com/a%a3do?q=r%c3%a9sum%c3%a9")),
                                          "http://www.example.com/a%A3do?q=r%C3%A9sum%C3%A9")

    def test_canonicalize_parse_url(self):
        # parse_url() wraps urlparse and is used in link extractors
        self.assertEqual(canonicalize_url(parse_url(u"http://www.example.com/résumé?q=résumé")),
                                          "http://www.example.com/r%C3%A9sum%C3%A9?q=r%C3%A9sum%C3%A9")
        self.assertEqual(canonicalize_url(parse_url('http://www.example.com/caf%e9-con-leche.htm')),
                                          'http://www.example.com/caf%E9-con-leche.htm')
        self.assertEqual(canonicalize_url(parse_url("http://www.example.com/a%a3do?q=r%c3%a9sum%c3%a9")),
                                          "http://www.example.com/a%A3do?q=r%C3%A9sum%C3%A9")

    def test_canonicalize_url_idempotence(self):
        for url, enc in [(u'http://www.bücher.de/résumé?q=résumé', 'utf8'),
                         (u'http://www.example.com/résumé?q=résumé', 'latin1'),
                         (u'http://www.example.com/résumé?country=Россия', 'cp1251'),
                         (u'http://はじめよう.みんな/?query=サ&maxResults=5', 'iso2022jp')]:
            canonicalized = canonicalize_url(url, encoding=enc)

            # if we canonicalize again, we ge the same result
            self.assertEqual(canonicalize_url(canonicalized, encoding=enc), canonicalized)

            # without encoding, already canonicalized URL is canonicalized identically
            self.assertEqual(canonicalize_url(canonicalized), canonicalized)


class AddHttpIfNoScheme(unittest.TestCase):

    def test_add_scheme(self):
        self.assertEqual(add_http_if_no_scheme('www.example.com'),
                                               'http://www.example.com')

    def test_without_subdomain(self):
        self.assertEqual(add_http_if_no_scheme('example.com'),
                                               'http://example.com')

    def test_path(self):
        self.assertEqual(add_http_if_no_scheme('www.example.com/some/page.html'),
                                               'http://www.example.com/some/page.html')

    def test_port(self):
        self.assertEqual(add_http_if_no_scheme('www.example.com:80'),
                                               'http://www.example.com:80')

    def test_fragment(self):
        self.assertEqual(add_http_if_no_scheme('www.example.com/some/page#frag'),
                                               'http://www.example.com/some/page#frag')

    def test_query(self):
        self.assertEqual(add_http_if_no_scheme('www.example.com/do?a=1&b=2&c=3'),
                                               'http://www.example.com/do?a=1&b=2&c=3')

    def test_username_password(self):
        self.assertEqual(add_http_if_no_scheme('username:password@www.example.com'),
                                               'http://username:password@www.example.com')

    def test_complete_url(self):
        self.assertEqual(add_http_if_no_scheme('username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag'),
                                               'http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag')

    def test_preserve_http(self):
        self.assertEqual(add_http_if_no_scheme('http://www.example.com'),
                                               'http://www.example.com')

    def test_preserve_http_without_subdomain(self):
        self.assertEqual(add_http_if_no_scheme('http://example.com'),
                                               'http://example.com')

    def test_preserve_http_path(self):
        self.assertEqual(add_http_if_no_scheme('http://www.example.com/some/page.html'),
                                               'http://www.example.com/some/page.html')

    def test_preserve_http_port(self):
        self.assertEqual(add_http_if_no_scheme('http://www.example.com:80'),
                                               'http://www.example.com:80')

    def test_preserve_http_fragment(self):
        self.assertEqual(add_http_if_no_scheme('http://www.example.com/some/page#frag'),
                                               'http://www.example.com/some/page#frag')

    def test_preserve_http_query(self):
        self.assertEqual(add_http_if_no_scheme('http://www.example.com/do?a=1&b=2&c=3'),
                                               'http://www.example.com/do?a=1&b=2&c=3')

    def test_preserve_http_username_password(self):
        self.assertEqual(add_http_if_no_scheme('http://username:password@www.example.com'),
                                               'http://username:password@www.example.com')

    def test_preserve_http_complete_url(self):
        self.assertEqual(add_http_if_no_scheme('http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag'),
                                               'http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag')

    def test_protocol_relative(self):
        self.assertEqual(add_http_if_no_scheme('//www.example.com'),
                                               'http://www.example.com')

    def test_protocol_relative_without_subdomain(self):
        self.assertEqual(add_http_if_no_scheme('//example.com'),
                                               'http://example.com')

    def test_protocol_relative_path(self):
        self.assertEqual(add_http_if_no_scheme('//www.example.com/some/page.html'),
                                               'http://www.example.com/some/page.html')

    def test_protocol_relative_port(self):
        self.assertEqual(add_http_if_no_scheme('//www.example.com:80'),
                                               'http://www.example.com:80')

    def test_protocol_relative_fragment(self):
        self.assertEqual(add_http_if_no_scheme('//www.example.com/some/page#frag'),
                                               'http://www.example.com/some/page#frag')

    def test_protocol_relative_query(self):
        self.assertEqual(add_http_if_no_scheme('//www.example.com/do?a=1&b=2&c=3'),
                                               'http://www.example.com/do?a=1&b=2&c=3')

    def test_protocol_relative_username_password(self):
        self.assertEqual(add_http_if_no_scheme('//username:password@www.example.com'),
                                               'http://username:password@www.example.com')

    def test_protocol_relative_complete_url(self):
        self.assertEqual(add_http_if_no_scheme('//username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag'),
                                               'http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag')

    def test_preserve_https(self):
        self.assertEqual(add_http_if_no_scheme('https://www.example.com'),
                                               'https://www.example.com')

    def test_preserve_ftp(self):
        self.assertEqual(add_http_if_no_scheme('ftp://www.example.com'),
                                               'ftp://www.example.com')


class GuessSchemeTest(unittest.TestCase):
    pass

def create_guess_scheme_t(args):
    def do_expected(self):
        url = guess_scheme(args[0])
        assert url.startswith(args[1]), \
            'Wrong scheme guessed: for `%s` got `%s`, expected `%s...`' % (
                args[0], url, args[1])
    return do_expected

def create_skipped_scheme_t(args):
    def do_expected(self):
        raise unittest.SkipTest(args[2])
        url = guess_scheme(args[0])
        assert url.startswith(args[1])
    return do_expected

for k, args in enumerate ([
            ('/index',                              'file://'),
            ('/index.html',                         'file://'),
            ('./index.html',                        'file://'),
            ('../index.html',                       'file://'),
            ('../../index.html',                    'file://'),
            ('./data/index.html',                   'file://'),
            ('.hidden/data/index.html',             'file://'),
            ('/home/user/www/index.html',           'file://'),
            ('//home/user/www/index.html',          'file://'),
            ('file:///home/user/www/index.html',    'file://'),

            ('index.html',                          'http://'),
            ('example.com',                         'http://'),
            ('www.example.com',                     'http://'),
            ('www.example.com/index.html',          'http://'),
            ('http://example.com',                  'http://'),
            ('http://example.com/index.html',       'http://'),
            ('localhost',                           'http://'),
            ('localhost/index.html',                'http://'),

            # some corner cases (default to http://)
            ('/',                                   'http://'),
            ('.../test',                            'http://'),

        ], start=1):
    t_method = create_guess_scheme_t(args)
    t_method.__name__ = 'test_uri_%03d' % k
    setattr (GuessSchemeTest, t_method.__name__, t_method)

# TODO: the following tests do not pass with current implementation
for k, args in enumerate ([
            ('C:\absolute\path\to\a\file.html',     'file://',
             'Windows filepath are not supported for scrapy shell'),
        ], start=1):
    t_method = create_skipped_scheme_t(args)
    t_method.__name__ = 'test_uri_skipped_%03d' % k
    setattr (GuessSchemeTest, t_method.__name__, t_method)


if __name__ == "__main__":
    unittest.main()
