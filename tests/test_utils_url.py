# -*- coding: utf-8 -*-
import unittest

from scrapy.spiders import Spider
from scrapy.utils.url import (url_is_from_any_domain, url_is_from_spider,
                              add_http_if_no_scheme, guess_scheme, strip_url)


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
        self.assertFalse(url_is_from_any_domain(url + '.testdomain.com', ['testdomain.com']))

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


for k, args in enumerate([
            ('/index', 'file://'),
            ('/index.html', 'file://'),
            ('./index.html', 'file://'),
            ('../index.html', 'file://'),
            ('../../index.html', 'file://'),
            ('./data/index.html', 'file://'),
            ('.hidden/data/index.html', 'file://'),
            ('/home/user/www/index.html', 'file://'),
            ('//home/user/www/index.html', 'file://'),
            ('file:///home/user/www/index.html', 'file://'),

            ('index.html', 'http://'),
            ('example.com', 'http://'),
            ('www.example.com', 'http://'),
            ('www.example.com/index.html', 'http://'),
            ('http://example.com', 'http://'),
            ('http://example.com/index.html', 'http://'),
            ('localhost', 'http://'),
            ('localhost/index.html', 'http://'),

            # some corner cases (default to http://)
            ('/', 'http://'),
            ('.../test', 'http://'),

        ], start=1):
    t_method = create_guess_scheme_t(args)
    t_method.__name__ = 'test_uri_%03d' % k
    setattr(GuessSchemeTest, t_method.__name__, t_method)

# TODO: the following tests do not pass with current implementation
for k, args in enumerate([
            (r'C:\absolute\path\to\a\file.html', 'file://',
             'Windows filepath are not supported for scrapy shell'),
        ], start=1):
    t_method = create_skipped_scheme_t(args)
    t_method.__name__ = 'test_uri_skipped_%03d' % k
    setattr(GuessSchemeTest, t_method.__name__, t_method)


class StripUrl(unittest.TestCase):

    def test_noop(self):
        self.assertEqual(strip_url(
            'http://www.example.com/index.html'),
            'http://www.example.com/index.html')

    def test_noop_query_string(self):
        self.assertEqual(strip_url(
            'http://www.example.com/index.html?somekey=somevalue'),
            'http://www.example.com/index.html?somekey=somevalue')

    def test_fragments(self):
        self.assertEqual(strip_url(
            'http://www.example.com/index.html?somekey=somevalue#section', strip_fragment=False),
            'http://www.example.com/index.html?somekey=somevalue#section')

    def test_path(self):
        for input_url, origin, output_url in [
            ('http://www.example.com/',
             False,
             'http://www.example.com/'),

            ('http://www.example.com',
             False,
             'http://www.example.com'),

            ('http://www.example.com',
             True,
             'http://www.example.com/'),
            ]:
            self.assertEqual(strip_url(input_url, origin_only=origin), output_url)

    def test_credentials(self):
        for i, o in [
            ('http://username@www.example.com/index.html?somekey=somevalue#section',
             'http://www.example.com/index.html?somekey=somevalue'),

            ('https://username:@www.example.com/index.html?somekey=somevalue#section',
             'https://www.example.com/index.html?somekey=somevalue'),

            ('ftp://username:password@www.example.com/index.html?somekey=somevalue#section',
             'ftp://www.example.com/index.html?somekey=somevalue'),
            ]:
            self.assertEqual(strip_url(i, strip_credentials=True), o)

    def test_credentials_encoded_delims(self):
        for i, o in [
            # user: "username@"
            # password: none
            ('http://username%40@www.example.com/index.html?somekey=somevalue#section',
             'http://www.example.com/index.html?somekey=somevalue'),

            # user: "username:pass"
            # password: ""
            ('https://username%3Apass:@www.example.com/index.html?somekey=somevalue#section',
             'https://www.example.com/index.html?somekey=somevalue'),

            # user: "me"
            # password: "user@domain.com"
            ('ftp://me:user%40domain.com@www.example.com/index.html?somekey=somevalue#section',
             'ftp://www.example.com/index.html?somekey=somevalue'),
            ]:
            self.assertEqual(strip_url(i, strip_credentials=True), o)

    def test_default_ports_creds_off(self):
        for i, o in [
            ('http://username:password@www.example.com:80/index.html?somekey=somevalue#section',
             'http://www.example.com/index.html?somekey=somevalue'),

            ('http://username:password@www.example.com:8080/index.html#section',
             'http://www.example.com:8080/index.html'),

            ('http://username:password@www.example.com:443/index.html?somekey=somevalue&someotherkey=sov#section',
             'http://www.example.com:443/index.html?somekey=somevalue&someotherkey=sov'),

            ('https://username:password@www.example.com:443/index.html',
             'https://www.example.com/index.html'),

            ('https://username:password@www.example.com:442/index.html',
             'https://www.example.com:442/index.html'),

            ('https://username:password@www.example.com:80/index.html',
             'https://www.example.com:80/index.html'),

            ('ftp://username:password@www.example.com:21/file.txt',
             'ftp://www.example.com/file.txt'),

            ('ftp://username:password@www.example.com:221/file.txt',
             'ftp://www.example.com:221/file.txt'),
            ]:
            self.assertEqual(strip_url(i), o)

    def test_default_ports(self):
        for i, o in [
            ('http://username:password@www.example.com:80/index.html',
             'http://username:password@www.example.com/index.html'),

            ('http://username:password@www.example.com:8080/index.html',
             'http://username:password@www.example.com:8080/index.html'),

            ('http://username:password@www.example.com:443/index.html',
             'http://username:password@www.example.com:443/index.html'),

            ('https://username:password@www.example.com:443/index.html',
             'https://username:password@www.example.com/index.html'),

            ('https://username:password@www.example.com:442/index.html',
             'https://username:password@www.example.com:442/index.html'),

            ('https://username:password@www.example.com:80/index.html',
             'https://username:password@www.example.com:80/index.html'),

            ('ftp://username:password@www.example.com:21/file.txt',
             'ftp://username:password@www.example.com/file.txt'),

            ('ftp://username:password@www.example.com:221/file.txt',
             'ftp://username:password@www.example.com:221/file.txt'),
            ]:
            self.assertEqual(strip_url(i, strip_default_port=True, strip_credentials=False), o)

    def test_default_ports_keep(self):
        for i, o in [
            ('http://username:password@www.example.com:80/index.html?somekey=somevalue&someotherkey=sov#section',
             'http://username:password@www.example.com:80/index.html?somekey=somevalue&someotherkey=sov'),

            ('http://username:password@www.example.com:8080/index.html?somekey=somevalue&someotherkey=sov#section',
             'http://username:password@www.example.com:8080/index.html?somekey=somevalue&someotherkey=sov'),

            ('http://username:password@www.example.com:443/index.html',
             'http://username:password@www.example.com:443/index.html'),

            ('https://username:password@www.example.com:443/index.html',
             'https://username:password@www.example.com:443/index.html'),

            ('https://username:password@www.example.com:442/index.html',
             'https://username:password@www.example.com:442/index.html'),

            ('https://username:password@www.example.com:80/index.html',
             'https://username:password@www.example.com:80/index.html'),

            ('ftp://username:password@www.example.com:21/file.txt',
             'ftp://username:password@www.example.com:21/file.txt'),

            ('ftp://username:password@www.example.com:221/file.txt',
             'ftp://username:password@www.example.com:221/file.txt'),
            ]:
            self.assertEqual(strip_url(i, strip_default_port=False, strip_credentials=False), o)

    def test_origin_only(self):
        for i, o in [
            ('http://username:password@www.example.com/index.html',
             'http://www.example.com/'),

            ('http://username:password@www.example.com:80/foo/bar?query=value#somefrag',
             'http://www.example.com/'),

            ('http://username:password@www.example.com:8008/foo/bar?query=value#somefrag',
             'http://www.example.com:8008/'),

            ('https://username:password@www.example.com:443/index.html',
             'https://www.example.com/'),
            ]:
            self.assertEqual(strip_url(i, origin_only=True), o)


if __name__ == "__main__":
    unittest.main()
