import os
import sys
from twisted.trial.unittest import TestCase, SkipTest

from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware
from scrapy.exceptions import NotConfigured
from scrapy.http import Response, Request
from scrapy.spiders import Spider

spider = Spider('foo')


class TestDefaultHeadersMiddleware(TestCase):

    failureException = AssertionError

    def setUp(self):
        self._oldenv = os.environ.copy()

    def tearDown(self):
        os.environ = self._oldenv

    def test_no_proxies(self):
        os.environ = {}
        self.assertRaises(NotConfigured, HttpProxyMiddleware)

    def test_no_enviroment_proxies(self):
        os.environ = {'dummy_proxy': 'reset_env_and_do_not_raise'}
        mw = HttpProxyMiddleware()

        for url in ('http://e.com', 'https://e.com', 'file:///tmp/a'):
            req = Request(url)
            assert mw.process_request(req, spider) is None
            self.assertEquals(req.url, url)
            self.assertEquals(req.meta, {})

    def test_enviroment_proxies(self):
        os.environ['http_proxy'] = http_proxy = 'https://proxy.for.http:3128'
        os.environ['https_proxy'] = https_proxy = 'http://proxy.for.https:8080'
        os.environ.pop('file_proxy', None)
        mw = HttpProxyMiddleware()

        for url, proxy in [('http://e.com', http_proxy),
                ('https://e.com', https_proxy), ('file://tmp/a', None)]:
            req = Request(url)
            assert mw.process_request(req, spider) is None
            self.assertEquals(req.url, url)
            self.assertEquals(req.meta.get('proxy'), proxy)

    def test_proxy_auth(self):
        os.environ['http_proxy'] = 'https://user:pass@proxy:3128'
        mw = HttpProxyMiddleware()
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEquals(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEquals(req.headers.get('Proxy-Authorization'), b'Basic dXNlcjpwYXNz')

    def test_proxy_auth_empty_passwd(self):
        os.environ['http_proxy'] = 'https://user:@proxy:3128'
        mw = HttpProxyMiddleware()
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEquals(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEquals(req.headers.get('Proxy-Authorization'), b'Basic dXNlcjo=')

    def test_proxy_auth_encoding(self):
        # utf-8 encoding
        os.environ['http_proxy'] = u'https://m\u00E1n:pass@proxy:3128'
        mw = HttpProxyMiddleware(auth_encoding='utf-8')
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEquals(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEquals(req.headers.get('Proxy-Authorization'), b'Basic bcOhbjpwYXNz')

        # default latin-1 encoding
        mw = HttpProxyMiddleware(auth_encoding='latin-1')
        req = Request('http://scrapytest.org')
        assert mw.process_request(req, spider) is None
        self.assertEquals(req.meta, {'proxy': 'https://proxy:3128'})
        self.assertEquals(req.headers.get('Proxy-Authorization'), b'Basic beFuOnBhc3M=')

    def test_proxy_already_seted(self):
        os.environ['http_proxy'] = http_proxy = 'https://proxy.for.http:3128'
        mw = HttpProxyMiddleware()
        req = Request('http://noproxy.com', meta={'proxy': None})
        assert mw.process_request(req, spider) is None
        assert 'proxy' in req.meta and req.meta['proxy'] is None

    def test_no_proxy(self):
        os.environ['http_proxy'] = http_proxy = 'https://proxy.for.http:3128'
        mw = HttpProxyMiddleware()

        os.environ['no_proxy'] = '*'
        req = Request('http://noproxy.com')
        assert mw.process_request(req, spider) is None
        assert 'proxy' not in req.meta

        os.environ['no_proxy'] = 'other.com'
        req = Request('http://noproxy.com')
        assert mw.process_request(req, spider) is None
        assert 'proxy' in req.meta

        os.environ['no_proxy'] = 'other.com,noproxy.com'
        req = Request('http://noproxy.com')
        assert mw.process_request(req, spider) is None
        assert 'proxy' not in req.meta
