import unittest

from scrapy.http import Request
from scrapy.downloadermiddlewares.auth import AuthMiddleware
from scrapy.spiders import Spider


class TestSpider(Spider):
    http_user = 'foo'
    http_pass = 'bar'


class AuthMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = AuthMiddleware()
        self.spider = TestSpider('foo')
        self.mw.spider_opened(self.spider)

    def tearDown(self):
        del self.mw

    def test_auth(self):
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers['Authorization'], b'Basic Zm9vOmJhcg==')

    def test_auth_already_set(self):
        req = Request('http://scrapytest.org/',
                      headers=dict(Authorization='Digest 123'))
        assert self.mw.process_request(req, self.spider) is None
        self.assertEquals(req.headers['Authorization'], b'Digest 123')
