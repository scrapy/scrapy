import unittest

from scrapy.contrib.downloadermiddleware.redirect import RedirectMiddleware
from scrapy.core.exceptions import HttpException
from scrapy.dupefilter import dupefilter
from scrapy.spider import spiders
from scrapy.http import Request, Response, Headers

class RedirectMiddlewareTest(unittest.TestCase):

    def setUp(self):
        spiders.spider_modules = ['scrapy.tests.test_spiders']
        spiders.reload()
        self.spider = spiders.fromdomain('scrapytest.org')
        dupefilter.open('scrapytest.org')
        self.mw = RedirectMiddleware()

    def tearDown(self):
        dupefilter.close('scrapytest.org')

    def test_redirect_301(self):
        url = 'http://www.example.com/301'
        url2 = 'http://www.example.com/redirected'
        req = Request(url)
        hdr = Headers({'Location': [url2]})
        rsp = Response(url, headers=hdr)
        exc = HttpException('301', None, rsp)

        req2 = self.mw.process_exception(req, exc, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)

        # response without Location header but with status code is 3XX should be ignored
        del rsp.headers['Location']
        assert self.mw.process_exception(req, exc, self.spider) is None

    def test_redirect_302(self):
        url = 'http://www.example.com/302'
        url2 = 'http://www.example.com/redirected2'
        req = Request(url, method='POST', body='test', 
            headers={'Content-Type': 'text/plain', 'Content-length': '4'})
        hdr = Headers({'Location': [url2]})
        rsp = Response(url, headers=hdr)
        exc = HttpException('302', None, rsp)

        req2 = self.mw.process_exception(req, exc, self.spider)
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
        assert self.mw.process_exception(req, exc, self.spider) is None

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
        exc = HttpException('302', None, Response('http://www.scrapytest.org/302', headers={'Location': '/redirected'}))

        req = self.mw.process_exception(req, exc, self.spider)
        assert isinstance(req, Request)
        assert 'redirect_times' in req.meta
        self.assertEqual(req.meta['redirect_times'], 1)

        req = self.mw.process_exception(req, exc, self.spider)
        self.assertEqual(req, None)

    def test_ttl(self):
        self.mw.max_redirect_times = 100
        req = Request('http://scrapytest.org/302', meta={'redirect_ttl': 1})
        exc = HttpException('302', None, Response('http://www.scrapytest.org/302', headers={'Location': '/redirected'}))

        req = self.mw.process_exception(req, exc, self.spider)
        assert isinstance(req, Request)
        req = self.mw.process_exception(req, exc, self.spider)
        self.assertEqual(req, None)

if __name__ == "__main__":
    unittest.main()
