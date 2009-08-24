import unittest

from scrapy.contrib.downloadermiddleware.redirect import RedirectMiddleware
from scrapy.spider import BaseSpider
from scrapy.core.exceptions import IgnoreRequest
from scrapy.http import Request, Response, Headers

class RedirectMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.spider = BaseSpider()
        self.mw = RedirectMiddleware()

    def test_priority_adjust(self):
        req = Request('http://a.com')
        rsp = Response('http://a.com', headers={'Location': 'http://a.com/redirected'}, status=301)
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert req2.priority > req.priority

    def test_redirect_301(self):
        url = 'http://www.example.com/301'
        url2 = 'http://www.example.com/redirected'
        req = Request(url)
        rsp = Response(url, headers={'Location': url2}, status=301)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)

        # response without Location header but with status code is 3XX should be ignored
        del rsp.headers['Location']
        assert self.mw.process_response(req, rsp, self.spider) is rsp

    def test_redirect_302(self):
        url = 'http://www.example.com/302'
        url2 = 'http://www.example.com/redirected2'
        req = Request(url, method='POST', body='test', 
            headers={'Content-Type': 'text/plain', 'Content-length': '4'})
        rsp = Response(url, headers={'Location': url2}, status=302)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)
        self.assertEqual(req2.method, 'GET')
        assert 'Content-Type' not in req2.headers, \
            "Content-Type header must not be present in redirected request"
        assert 'Content-Length' not in req2.headers, \
            "Content-Length header must not be present in redirected request"
        assert not req2.body, \
            "Redirected body must be empty, not '%s'" % req2.body

        # response without Location header but with status code is 3XX should be ignored
        del rsp.headers['Location']
        assert self.mw.process_response(req, rsp, self.spider) is rsp

    def test_meta_refresh(self):
        body = """<html>
            <head><meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
            </html>"""
        req = Request(url='http://example.org')
        rsp = Response(url='http://example.org', body=body)
        req2 = self.mw.process_response(req, rsp, self.spider)

        assert isinstance(req2, Request)
        self.assertEqual(req2.url, 'http://example.org/newpage')

        # meta-refresh with high intervals don't trigger redirects
        body = """<html>
            <head><meta http-equiv="refresh" content="1000;url=http://example.org/newpage" /></head>
            </html>"""
        req = Request(url='http://example.org')
        rsp = Response(url='http://example.org', body=body)
        rsp2 = self.mw.process_response(req, rsp, self.spider)

        assert rsp is rsp2

    def test_max_redirect_times(self):
        self.mw.max_redirect_times = 1
        req = Request('http://scrapytest.org/302')
        rsp = Response('http://scrapytest.org/302', headers={'Location': '/redirected'}, status=302)

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        assert 'redirect_times' in req.meta
        self.assertEqual(req.meta['redirect_times'], 1)
        self.assertRaises(IgnoreRequest, self.mw.process_response, req, rsp, self.spider)

    def test_ttl(self):
        self.mw.max_redirect_times = 100
        req = Request('http://scrapytest.org/302', meta={'redirect_ttl': 1})
        rsp = Response('http://www.scrapytest.org/302', headers={'Location': '/redirected'}, status=302)

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        self.assertRaises(IgnoreRequest, self.mw.process_response, req, rsp, self.spider)

if __name__ == "__main__":
    unittest.main()
