import os
import sys
from functools import partial
from twisted.trial.unittest import TestCase, SkipTest

from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware, basic_auth_header, get_proxy
from scrapy.exceptions import NotConfigured
from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.crawler import Crawler
from scrapy.settings import Settings

spider = Spider('foo')


class TestHttpProxyMiddleware(TestCase):

    failureException = AssertionError

    def setUp(self):
        self._oldenv = os.environ.copy()

    def tearDown(self):
        os.environ = self._oldenv

    def test_not_enabled(self):
        settings = Settings({'HTTPPROXY_ENABLED': False})
        crawler = Crawler(Spider, settings)
        self.assertRaises(NotConfigured, partial(HttpProxyMiddleware.from_crawler, crawler))

    def test_no_environment_proxies(self):
        os.environ = {'dummy_proxy': 'reset_env_and_do_not_raise'}

        for url in ('http://e.com', 'https://e.com', 'file:///tmp/a'):
            mw = HttpProxyMiddleware()
            basic_auth_header.cache_clear()
            get_proxy.cache_clear()

            req = Request(url)
            assert mw.process_request(req, spider) is None
            self.assertEqual(req.url, url)
            self.assertEqual(req.meta, {})

    def test_environment_proxies(self):
        os.environ['http_proxy'] = http_proxy = 'https://proxy.for.http:3128'
        os.environ['https_proxy'] = https_proxy = 'http://proxy.for.https:8080'
        os.environ.pop('file_proxy', None)

        for url, proxy in [('http://e.com', http_proxy),
                ('https://e.com', https_proxy), ('file://tmp/a', None)]:
            req = Request(url)

            mw = HttpProxyMiddleware()
            basic_auth_header.cache_clear()
            get_proxy.cache_clear()

            assert mw.process_request(req, spider) is None
            self.assertEqual(req.url, url)
            self.assertEqual(req.meta.get('proxy'), proxy)

    def test_proxy_precedence_meta(self):
        os.environ['http_proxy'] = 'https://proxy.com'
        mw = HttpProxyMiddleware()
        req = Request('http://scrapytest.org', meta={'proxy': 'https://new.proxy:3128'})
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://new.proxy:3128'})

    def test_proxy_auth(self):
        os.environ['http_proxy'] = 'https://user:pass@proxy:3128'
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic dXNlcjpwYXNz')
        # proxy from request.meta
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org', meta={'proxy': 'https://username:password@proxy:3128'})
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic dXNlcm5hbWU6cGFzc3dvcmQ=')

    def test_proxy_auth_empty_passwd(self):
        os.environ['http_proxy'] = 'https://user:@proxy:3128'
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic dXNlcjo=')
        # proxy from request.meta
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org', meta={'proxy': 'https://username:@proxy:3128'})
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic dXNlcm5hbWU6')

    def test_proxy_auth_encoding(self):
        # utf-8 encoding
        os.environ['http_proxy'] = u'https://m\u00E1n:pass@proxy:3128'
        mw = HttpProxyMiddleware(auth_encoding='utf-8')
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic bcOhbjpwYXNz')

        # proxy from request.meta
        mw = HttpProxyMiddleware(auth_encoding='utf-8')
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org', meta={'proxy': u'https://\u00FCser:pass@proxy:3128'})
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic w7xzZXI6cGFzcw==')

        # default latin-1 encoding
        mw = HttpProxyMiddleware(auth_encoding='latin-1')
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic beFuOnBhc3M=')

        # proxy from request.meta, latin-1 encoding
        mw = HttpProxyMiddleware(auth_encoding='latin-1')
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://scrapytest.org', meta={'proxy': u'https://\u00FCser:pass@proxy:3128'})
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEqual(req.headers.get('Proxy-Authorization'), b'Basic /HNlcjpwYXNz')

    def test_proxy_already_seted(self):
        os.environ['http_proxy'] = 'https://proxy.for.http:3128'
        mw = HttpProxyMiddleware()
        req = Request('http://noproxy.com', meta={'proxy': None})
        assert mw.process_request(req, spider) is None
        assert 'proxy' in req.meta and req.meta['proxy'] is None

    def test_no_proxy(self):
        os.environ['http_proxy'] = 'https://proxy.for.http:3128'
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()

        os.environ['no_proxy'] = '*'
        req = Request('http://noproxy.com')
        assert mw.process_request(req, spider) is None
        assert 'proxy' not in req.meta

        os.environ['no_proxy'] = 'other.com'
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://noproxy.com')
        assert mw.process_request(req, spider) is None
        assert 'proxy' in req.meta

        os.environ['no_proxy'] = 'other.com,noproxy.com'
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://noproxy.com')
        assert mw.process_request(req, spider) is None
        assert 'proxy' not in req.meta

        # proxy from meta['proxy'] takes precedence
        os.environ['no_proxy'] = '*'
        mw = HttpProxyMiddleware()
        basic_auth_header.cache_clear()
        get_proxy.cache_clear()
        req = Request('http://noproxy.com', meta={'proxy': 'http://proxy.com'})
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta, {'proxy': 'http://proxy.com'})
