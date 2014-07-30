import unittest

from scrapy.contrib.downloadermiddleware.ajaxcrawl import AjaxCrawlMiddleware
from scrapy.spider import Spider
from scrapy.http import Request, HtmlResponse, Response
from scrapy.utils.test import get_crawler

__doctests__ = ['scrapy.contrib.downloadermiddleware.ajaxcrawl']

class AjaxCrawlMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.spider = Spider('foo')
        crawler = get_crawler({'AJAXCRAWL_ENABLED': True})
        self.mw = AjaxCrawlMiddleware.from_crawler(crawler)

    def _ajaxcrawlable_body(self):
        return '<html><head><meta name="fragment" content="!"/></head><body></body></html>'

    def _req_resp(self, url, req_kwargs=None, resp_kwargs=None):
        req = Request(url, **(req_kwargs or {}))
        resp = HtmlResponse(url, request=req, **(resp_kwargs or {}))
        return req, resp

    def test_non_get(self):
        req, resp = self._req_resp('http://example.com/', {'method': 'HEAD'})
        resp2 = self.mw.process_response(req, resp, self.spider)
        self.assertEqual(resp, resp2)

    def test_binary_response(self):
        req = Request('http://example.com/')
        resp = Response('http://example.com/', body=b'foobar\x00\x01\x02', request=req)
        resp2 = self.mw.process_response(req, resp, self.spider)
        self.assertIs(resp, resp2)

    def test_ajaxcrawl(self):
        req, resp = self._req_resp(
            'http://example.com/',
            {'meta': {'foo': 'bar'}},
            {'body': self._ajaxcrawlable_body()}
        )
        req2 = self.mw.process_response(req, resp, self.spider)
        self.assertEqual(req2.url, 'http://example.com/?_escaped_fragment_=')
        self.assertEqual(req2.meta['foo'], 'bar')

    def test_ajaxcrawl_loop(self):
        req, resp = self._req_resp('http://example.com/', {}, {'body': self._ajaxcrawlable_body()})
        req2 = self.mw.process_response(req, resp, self.spider)
        resp2 = HtmlResponse(req2.url, body=resp.body, request=req2)
        resp3 = self.mw.process_response(req2, resp2, self.spider)

        assert isinstance(resp3, HtmlResponse), (resp3.__class__, resp3)
        self.assertEqual(resp3.request.url, 'http://example.com/?_escaped_fragment_=')
        assert resp3 is resp2

    def test_noncrawlable_body(self):
        req, resp = self._req_resp('http://example.com/', {}, {'body': '<html></html>'})
        resp2 = self.mw.process_response(req, resp, self.spider)
        self.assertIs(resp, resp2)
