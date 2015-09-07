# -*- coding: utf-8 -*-
import unittest

import six
from scrapy.spiders import Spider
from scrapy.utils.url import (url_is_from_any_domain, url_is_from_spider,
                              canonicalize_url)

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

    @unittest.skipUnless(six.PY2, "TODO")
    def test_normalize_percent_encoding_in_paths(self):
        self.assertEqual(canonicalize_url("http://www.example.com/a%a3do"),
                                          "http://www.example.com/a%A3do"),

    @unittest.skipUnless(six.PY2, "TODO")
    def test_normalize_percent_encoding_in_query_arguments(self):
        self.assertEqual(canonicalize_url("http://www.example.com/do?k=b%a3"),
                                          "http://www.example.com/do?k=b%A3")

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
        self.assertEqual(canonicalize_url(u"http://www.example.com/do?price=\xa3500&a=5&z=3"),
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

    @unittest.skipUnless(six.PY2, "TODO")
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

    def test_quoted_slash_and_question_sign(self):
        self.assertEqual(canonicalize_url("http://foo.com/AC%2FDC+rocks%3f/?yeah=1"),
                         "http://foo.com/AC%2FDC+rocks%3F/?yeah=1")
        self.assertEqual(canonicalize_url("http://foo.com/AC%2FDC/"),
                         "http://foo.com/AC%2FDC/")


if __name__ == "__main__":
    unittest.main()
