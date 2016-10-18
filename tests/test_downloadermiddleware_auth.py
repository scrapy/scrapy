import unittest

from scrapy.http import Request
from scrapy.downloadermiddlewares.auth import AuthMiddleware
from scrapy.spiders import Spider


class TestSpider(Spider):
    http_user = 'foo'
    http_pass = 'bar'


class NoAuthTestSpider(Spider):
    """A test spider that does not set http auth atttributes"""


class AuthMiddlewareNoAuthTest(unittest.TestCase):

    def setUp(self):
        self.mw = AuthMiddleware()
        self.spider = NoAuthTestSpider('bar')
        self.mw.spider_opened(self.spider)

    def tearDown(self):
        del self.mw

    def test_no_auth_http(self):
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertNotIn('Authorization', req.headers)

    def test_no_auth_ftp(self):
        req = Request('ftp://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertNotIn('ftp_user', req.meta)
        self.assertNotIn('ftp_password', req.meta)


class AuthMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = AuthMiddleware()
        self.spider = TestSpider('foo')
        self.mw.spider_opened(self.spider)

    def tearDown(self):
        del self.mw


class AuthMiddlewareHttpAuthTest(AuthMiddlewareTest):

    def test_auth(self):
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers['Authorization'], b'Basic Zm9vOmJhcg==')

    def test_auth_already_set(self):
        req = Request('http://scrapytest.org/',
                      headers=dict(Authorization='Digest 123'))
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers['Authorization'], b'Digest 123')

    def test_auth_from_http_url(self):
        req = Request('http://username:password@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(new_req.headers['Authorization'], b'Basic dXNlcm5hbWU6cGFzc3dvcmQ=')
        self.assertEquals(new_req.url, 'http://scrapytest.org/')

    def test_auth_from_https_url(self):
        req = Request('https://username:password@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(new_req.headers['Authorization'], b'Basic dXNlcm5hbWU6cGFzc3dvcmQ=')
        self.assertEquals(new_req.url, 'https://scrapytest.org/')

    def test_auth_from_http_url_no_spider_attrs(self):
        class AnotherTestSpider(Spider):
            pass
        req = Request('http://username:password@scrapytest.org/')
        new_req = self.mw.process_request(req, AnotherTestSpider('bar'))
        assert new_req is not None
        self.assertEquals(new_req.headers['Authorization'], b'Basic dXNlcm5hbWU6cGFzc3dvcmQ=')
        self.assertEquals(new_req.url, 'http://scrapytest.org/')

    def test_auth_from_https_url_no_spider_attrs(self):
        class AnotherTestSpider(Spider):
            pass
        req = Request('https://username:password@scrapytest.org/')
        new_req = self.mw.process_request(req, AnotherTestSpider('bar'))
        assert new_req is not None
        self.assertEquals(new_req.headers['Authorization'], b'Basic dXNlcm5hbWU6cGFzc3dvcmQ=')
        self.assertEquals(new_req.url, 'https://scrapytest.org/')

    def test_auth_from_http_url_empty_pass(self):
        req = Request('http://username:@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(new_req.headers['Authorization'], b'Basic dXNlcm5hbWU6')
        self.assertEquals(new_req.url, 'http://scrapytest.org/')

    def test_auth_from_http_url_pass_none(self):
        req = Request('http://username@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(new_req.headers['Authorization'], b'Basic dXNlcm5hbWU6Tm9uZQ==')
        self.assertEquals(new_req.url, 'http://scrapytest.org/')

    def test_auth_from_http_url_empty_user(self):
        req = Request('http://:password@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(new_req.headers['Authorization'], b'Basic OnBhc3N3b3Jk')
        self.assertEquals(new_req.url, 'http://scrapytest.org/')


class AuthMiddlewareFtpAuthTest(AuthMiddlewareTest):

    def test_no_auth_from_ftp_url_meta_unchanged(self):
        usr, pwd = 'u', 'p'
        req = Request('ftp://scrapytest.org/',
                      meta={"ftp_user": usr, "ftp_password": pwd})
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.meta['ftp_user'], usr)
        self.assertEquals(req.meta['ftp_password'], pwd)

    def test_auth_from_ftp_url_meta_unchanged(self):
        """Request's meta credentials are kept as-is,
        but URL is stripped from credentials
        """
        usr, pwd = 'u', 'p'
        req = Request('ftp://username:password@scrapytest.org/',
                      meta={"ftp_user": usr, "ftp_password": pwd})
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(new_req.meta['ftp_user'], usr)
        self.assertEquals(new_req.meta['ftp_password'], pwd)
        self.assertEquals(new_req.url, 'ftp://scrapytest.org/')

    def test_auth_from_ftp_url(self):
        req = Request('ftp://username:password@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(req.meta['ftp_user'], 'username')
        self.assertEquals(req.meta['ftp_password'], 'password')
        self.assertEquals(new_req.url, 'ftp://scrapytest.org/')

    def test_auth_from_ftp_url_empty_user(self):
        req = Request('ftp://:password@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(req.meta['ftp_user'], '')
        self.assertEquals(req.meta['ftp_password'], 'password')
        self.assertEquals(new_req.url, 'ftp://scrapytest.org/')

    def test_auth_from_ftp_url_empty_pass(self):
        req = Request('ftp://username:@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(req.meta['ftp_user'], 'username')
        self.assertEquals(req.meta['ftp_password'], '')
        self.assertEquals(new_req.url, 'ftp://scrapytest.org/')

    def test_auth_from_ftp_url_pass_none(self):
        req = Request('ftp://username@scrapytest.org/')
        new_req = self.mw.process_request(req, self.spider)
        assert new_req is not None
        self.assertEquals(req.meta['ftp_user'], 'username')
        self.assertEquals(req.meta['ftp_password'], None)
        self.assertEquals(new_req.url, 'ftp://scrapytest.org/')
