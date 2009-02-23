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

    def tearDown(self):
        dupefilter.close('scrapytest.org')

    def test_process_exception(self):

        mw = RedirectMiddleware()

        url = 'http://www.example.com/301'
        url2 = 'http://www.example.com/redirected'
        req = Request(url)
        hdr = Headers({'Location': [url2]})
        rsp = Response(url, headers=hdr)
        exc = HttpException('301', None, rsp)

        req2 = mw.process_exception(req, exc, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)

        url = 'http://www.example.com/302'
        url2 = 'http://www.example.com/redirected2'
        req = Request(url, method='POST')
        hdr = Headers({'Location': [url2]})
        rsp = Response(url, headers=hdr)
        exc = HttpException('302', None, rsp)

        req2 = mw.process_exception(req, exc, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)
        self.assertEqual(req2.method, 'GET')
        assert not req2.body

    def test_process_response(self):

        mw = RedirectMiddleware()

        body = """<html>
            <head><meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
            </html>"""
        req = Request(url='http://example.org')
        rsp = Response(url='http://example.org', body=body)
        req2 = mw.process_response(req, rsp, self.spider)

        assert isinstance(req2, Request)
        self.assertEqual(req2.url, 'http://example.org/newpage')

        # meta-refresh with high intervals don't trigger redirects
        body = """<html>
            <head><meta http-equiv="refresh" content="1000;url=http://example.org/newpage" /></head>
            </html>"""
        req = Request(url='http://example.org')
        rsp = Response(url='http://example.org', body=body)
        rsp2 = mw.process_response(req, rsp, self.spider)

        assert rsp is rsp2

if __name__ == "__main__":
    unittest.main()
