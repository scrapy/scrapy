import unittest

from scrapy.http import Request
from scrapy.contrib.downloadermiddleware.httpauth import HttpAuthMiddleware
from scrapy.spider import BaseSpider

class TestSpider(BaseSpider):
    http_user = 'foo'
    http_pass = 'bar'

class HttpAuthMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = HttpAuthMiddleware()

    def tearDown(self):
        del self.mw

    def test_auth(self):
        self.mw.default_useragent = 'default_useragent'
        spider = TestSpider('foo')
        req = Request('http://scrapytest.org/')
        assert self.mw.process_request(req, spider) is None
        self.assertEquals(req.headers['Authorization'], 'Basic Zm9vOmJhcg==')


if __name__ == '__main__':
    unittest.main()
