import unittest

from scrapy.contrib.downloadermiddleware.redirect import RedirectMiddleware, MetaRefreshMiddleware
from scrapy.spider import Spider
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response, HtmlResponse
from scrapy.utils.test import get_crawler


class RedirectMiddlewareTest(unittest.TestCase):

    def setUp(self):
        crawler = get_crawler()
        self.spider = Spider('foo')
        self.mw = RedirectMiddleware.from_crawler(crawler)

    def test_priority_adjust(self):
        req = Request('http://a.com')
        rsp = Response('http://a.com', headers={'Location': 'http://a.com/redirected'}, status=301)
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert req2.priority > req.priority

    def test_redirect_301(self):
        def _test(method):
            url = 'http://www.example.com/301'
            url2 = 'http://www.example.com/redirected'
            req = Request(url, method=method)
            rsp = Response(url, headers={'Location': url2}, status=301)

            req2 = self.mw.process_response(req, rsp, self.spider)
            assert isinstance(req2, Request)
            self.assertEqual(req2.url, url2)
            self.assertEqual(req2.method, method)

            # response without Location header but with status code is 3XX should be ignored
            del rsp.headers['Location']
            assert self.mw.process_response(req, rsp, self.spider) is rsp

        _test('GET')
        _test('POST')
        _test('HEAD')

    def test_dont_redirect(self):
        url = 'http://www.example.com/301'
        url2 = 'http://www.example.com/redirected'
        req = Request(url, meta={'dont_redirect': True})
        rsp = Response(url, headers={'Location': url2}, status=301)

        r = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(r, Response)
        assert r is rsp

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

    def test_redirect_302_head(self):
        url = 'http://www.example.com/302'
        url2 = 'http://www.example.com/redirected2'
        req = Request(url, method='HEAD')
        rsp = Response(url, headers={'Location': url2}, status=302)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)
        self.assertEqual(req2.method, 'HEAD')

        # response without Location header but with status code is 3XX should be ignored
        del rsp.headers['Location']
        assert self.mw.process_response(req, rsp, self.spider) is rsp


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

    def test_redirect_urls(self):
        req1 = Request('http://scrapytest.org/first')
        rsp1 = Response('http://scrapytest.org/first', headers={'Location': '/redirected'}, status=302)
        req2 = self.mw.process_response(req1, rsp1, self.spider)
        rsp2 = Response('http://scrapytest.org/redirected', headers={'Location': '/redirected2'}, status=302)
        req3 = self.mw.process_response(req2, rsp2, self.spider)

        self.assertEqual(req2.url, 'http://scrapytest.org/redirected')
        self.assertEqual(req2.meta['redirect_urls'], ['http://scrapytest.org/first'])
        self.assertEqual(req3.url, 'http://scrapytest.org/redirected2')
        self.assertEqual(req3.meta['redirect_urls'], ['http://scrapytest.org/first', 'http://scrapytest.org/redirected'])

class MetaRefreshMiddlewareTest(unittest.TestCase):

    def setUp(self):
        crawler = get_crawler()
        self.spider = Spider('foo')
        self.mw = MetaRefreshMiddleware.from_crawler(crawler)

    def _body(self, interval=5, url='http://example.org/newpage'):
        return """<html><head><meta http-equiv="refresh" content="{0};url={1}"/></head></html>"""\
                .format(interval, url)

    def test_priority_adjust(self):
        req = Request('http://a.com')
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert req2.priority > req.priority

    def test_meta_refresh(self):
        req = Request(url='http://example.org')
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, 'http://example.org/newpage')

    def test_meta_refresh_with_high_interval(self):
        # meta-refresh with high intervals don't trigger redirects
        req = Request(url='http://example.org')
        rsp = HtmlResponse(url='http://example.org', body=self._body(interval=1000))
        rsp2 = self.mw.process_response(req, rsp, self.spider)
        assert rsp is rsp2

    def test_meta_refresh_trough_posted_request(self):
        req = Request(url='http://example.org', method='POST', body='test',
                      headers={'Content-Type': 'text/plain', 'Content-length': '4'})
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)

        assert isinstance(req2, Request)
        self.assertEqual(req2.url, 'http://example.org/newpage')
        self.assertEqual(req2.method, 'GET')
        assert 'Content-Type' not in req2.headers, \
            "Content-Type header must not be present in redirected request"
        assert 'Content-Length' not in req2.headers, \
            "Content-Length header must not be present in redirected request"
        assert not req2.body, \
            "Redirected body must be empty, not '%s'" % req2.body

    def test_max_redirect_times(self):
        self.mw.max_redirect_times = 1
        req = Request('http://scrapytest.org/max')
        rsp = HtmlResponse(req.url, body=self._body())

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        assert 'redirect_times' in req.meta
        self.assertEqual(req.meta['redirect_times'], 1)
        self.assertRaises(IgnoreRequest, self.mw.process_response, req, rsp, self.spider)

    def test_ttl(self):
        self.mw.max_redirect_times = 100
        req = Request('http://scrapytest.org/302', meta={'redirect_ttl': 1})
        rsp = HtmlResponse(req.url, body=self._body())

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        self.assertRaises(IgnoreRequest, self.mw.process_response, req, rsp, self.spider)

    def test_redirect_urls(self):
        req1 = Request('http://scrapytest.org/first')
        rsp1 = HtmlResponse(req1.url, body=self._body(url='/redirected'))
        req2 = self.mw.process_response(req1, rsp1, self.spider)
        assert isinstance(req2, Request), req2
        rsp2 = HtmlResponse(req2.url, body=self._body(url='/redirected2'))
        req3 = self.mw.process_response(req2, rsp2, self.spider)
        assert isinstance(req3, Request), req3
        self.assertEqual(req2.url, 'http://scrapytest.org/redirected')
        self.assertEqual(req2.meta['redirect_urls'], ['http://scrapytest.org/first'])
        self.assertEqual(req3.url, 'http://scrapytest.org/redirected2')
        self.assertEqual(req3.meta['redirect_urls'], ['http://scrapytest.org/first', 'http://scrapytest.org/redirected'])

if __name__ == "__main__":
    unittest.main()
