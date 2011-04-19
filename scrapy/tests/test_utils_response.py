import os
import unittest
import urlparse

from scrapy.xlib.BeautifulSoup import BeautifulSoup
from scrapy.http import Response, TextResponse, HtmlResponse
from scrapy.utils.response import body_or_str, get_base_url, get_meta_refresh, \
    response_httprepr, get_cached_beautifulsoup, open_in_browser

__doctests__ = ['scrapy.utils.response']

class ResponseUtilsTest(unittest.TestCase):
    dummy_response = TextResponse(url='http://example.org/', body='dummy_response')

    def test_body_or_str_input(self):
        self.assertTrue(isinstance(body_or_str(self.dummy_response), basestring))
        self.assertTrue(isinstance(body_or_str('text'), basestring))
        self.assertRaises(Exception, body_or_str, 2)

    def test_body_or_str_extraction(self):
        self.assertEqual(body_or_str(self.dummy_response), 'dummy_response')
        self.assertEqual(body_or_str('text'), 'text')

    def test_body_or_str_encoding(self):
        self.assertTrue(isinstance(body_or_str(self.dummy_response, unicode=False), str))
        self.assertTrue(isinstance(body_or_str(self.dummy_response, unicode=True), unicode))

        self.assertTrue(isinstance(body_or_str('text', unicode=False), str))
        self.assertTrue(isinstance(body_or_str('text', unicode=True), unicode))

        self.assertTrue(isinstance(body_or_str(u'text', unicode=False), str))
        self.assertTrue(isinstance(body_or_str(u'text', unicode=True), unicode))

    def test_response_httprepr(self):
        r1 = Response("http://www.example.com")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 200 OK\r\n\r\n')

        r1 = Response("http://www.example.com", status=404, headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\nSome body')

        r1 = Response("http://www.example.com", status=6666, headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 6666 \r\nContent-Type: text/html\r\n\r\nSome body')

    def test_get_cached_beautifulsoup(self):
        r1 = Response('http://www.example.com', body='')

        soup1 = get_cached_beautifulsoup(r1)
        soup2 = get_cached_beautifulsoup(r1)

        assert isinstance(soup1, BeautifulSoup)
        assert isinstance(soup2, BeautifulSoup)
        # make sure it's cached
        assert soup1 is soup2

        # when body is None, an empty soup should be returned
        r1 = Response('http://www.example.com')
        assert r1.body == ""
        assert isinstance(get_cached_beautifulsoup(r1), BeautifulSoup)

        r1 = Response('http://www.example.com', body='')
        soup1 = get_cached_beautifulsoup(r1)
        r2 = r1.copy()
        soup2 = get_cached_beautifulsoup(r1)
        soup3 = get_cached_beautifulsoup(r2)

        assert soup1 is soup2
        assert soup1 is not soup3

    def test_open_in_browser(self):
        url = "http:///www.example.com/some/page.html"
        body = "<html> <head> <title>test page</title> </head> <body>test body</body> </html>"
        def browser_open(burl):
            path = urlparse.urlparse(burl).path
            if not os.path.exists(path):
                path = burl.replace('file://', '')
            bbody = open(path).read()
            assert '<base href="%s">' % url in bbody, "<base> tag not added"
            return True
        response = HtmlResponse(url, body=body)
        assert open_in_browser(response, _openfunc=browser_open), \
            "Browser not called"
        self.assertRaises(TypeError, open_in_browser, Response(url, body=body), \
            debug=True)

if __name__ == "__main__":
    unittest.main()
