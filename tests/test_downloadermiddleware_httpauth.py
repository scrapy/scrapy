import unittest

from w3lib.http import basic_auth_header

from scrapy.http import Request
from scrapy.downloadermiddlewares.httpauth import HttpAuthMiddleware
from scrapy.spiders import Spider


class TestSpiderLegacy(Spider):
    http_user = 'foo'
    http_pass = 'bar'


class TestSpider(Spider):
    http_user = 'foo'
    http_pass = 'bar'
    http_auth_domain = 'example.com'


class TestSpiderAny(Spider):
    http_user = 'foo'
    http_pass = 'bar'
    http_auth_domain = None


class HttpAuthMiddlewareLegacyTest(unittest.TestCase):

    def setUp(self):
        self.spider = TestSpiderLegacy('foo')

    def test_auth(self):
        mw = HttpAuthMiddleware()
        mw.spider_opened(self.spider)

        # initial request, sets the domain and sends the header
        req = Request('http://example.com/')
        assert mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], basic_auth_header('foo', 'bar'))

        # subsequent request to the same domain, should send the header
        req = Request('http://example.com/')
        assert mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], basic_auth_header('foo', 'bar'))

        # subsequent request to a different domain, shouldn't send the header
        req = Request('http://example-noauth.com/')
        assert mw.process_request(req, self.spider) is None
        self.assertNotIn('Authorization', req.headers)

    def test_auth_already_set(self):
        mw = HttpAuthMiddleware()
        mw.spider_opened(self.spider)
        req = Request('http://example.com/',
                      headers=dict(Authorization='Digest 123'))
        assert mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], b'Digest 123')


class HttpAuthMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = HttpAuthMiddleware()
        self.spider = TestSpider('foo')
        self.mw.spider_opened(self.spider)

    def tearDown(self):
        del self.mw

    def test_no_auth(self):
        req = Request('http://example-noauth.com/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertNotIn('Authorization', req.headers)

    def test_auth_domain(self):
        req = Request('http://example.com/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], basic_auth_header('foo', 'bar'))

    def test_auth_subdomain(self):
        req = Request('http://foo.example.com/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], basic_auth_header('foo', 'bar'))

    def test_auth_already_set(self):
        req = Request('http://example.com/',
                      headers=dict(Authorization='Digest 123'))
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], b'Digest 123')


class HttpAuthAnyMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = HttpAuthMiddleware()
        self.spider = TestSpiderAny('foo')
        self.mw.spider_opened(self.spider)

    def tearDown(self):
        del self.mw

    def test_auth(self):
        req = Request('http://example.com/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], basic_auth_header('foo', 'bar'))

    def test_auth_already_set(self):
        req = Request('http://example.com/',
                      headers=dict(Authorization='Digest 123'))
        assert self.mw.process_request(req, self.spider) is None
        self.assertEqual(req.headers['Authorization'], b'Digest 123')
