import os
import unittest
from urllib.parse import urlparse

from scrapy.http import Response, TextResponse, HtmlResponse
from scrapy.utils.python import to_bytes
from scrapy.utils.response import (response_httprepr, open_in_browser,
                                   get_meta_refresh, get_base_url, response_status_message)


__doctests__ = ['scrapy.utils.response']


class ResponseUtilsTest(unittest.TestCase):
    dummy_response = TextResponse(url='http://example.org/', body=b'dummy_response')

    def test_response_httprepr(self):
        r1 = Response("http://www.example.com")
        self.assertEqual(response_httprepr(r1), b'HTTP/1.1 200 OK\r\n\r\n')

        r1 = Response("http://www.example.com", status=404, headers={"Content-type": "text/html"}, body=b"Some body")
        self.assertEqual(response_httprepr(r1), b'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\nSome body')

        r1 = Response("http://www.example.com", status=6666, headers={"Content-type": "text/html"}, body=b"Some body")
        self.assertEqual(response_httprepr(r1), b'HTTP/1.1 6666 \r\nContent-Type: text/html\r\n\r\nSome body')

    def test_open_in_browser(self):
        url = "http:///www.example.com/some/page.html"
        body = b"<html> <head> <title>test page</title> </head> <body>test body</body> </html>"

        def browser_open(burl):
            path = urlparse(burl).path
            if not os.path.exists(path):
                path = burl.replace('file://', '')
            with open(path, "rb") as f:
                bbody = f.read()
            self.assertIn(b'<base href="' + to_bytes(url) + b'">', bbody)
            return True
        response = HtmlResponse(url, body=body)
        assert open_in_browser(response, _openfunc=browser_open), \
            "Browser not called"

        resp = Response(url, body=body)
        self.assertRaises(TypeError, open_in_browser, resp, debug=True)

    def test_get_meta_refresh(self):
        r1 = HtmlResponse("http://www.example.com", body=b"""
        <html>
        <head><title>Dummy</title><meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        <body>blahablsdfsal&amp;</body>
        </html>""")
        r2 = HtmlResponse("http://www.example.com", body=b"""
        <html>
        <head><title>Dummy</title><noScript>
        <meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        </noSCRIPT>
        <body>blahablsdfsal&amp;</body>
        </html>""")
        r3 = HtmlResponse("http://www.example.com", body=b"""
    <noscript><meta http-equiv="REFRESH" content="0;url=http://www.example.com/newpage</noscript>
    <script type="text/javascript">
    if(!checkCookies()){
        document.write('<meta http-equiv="REFRESH" content="0;url=http://www.example.com/newpage">');
    }
    </script>
        """)
        self.assertEqual(get_meta_refresh(r1), (5.0, 'http://example.org/newpage'))
        self.assertEqual(get_meta_refresh(r2), (None, None))
        self.assertEqual(get_meta_refresh(r3), (None, None))

    def test_get_base_url(self):
        resp = HtmlResponse("http://www.example.com", body=b"""
        <html>
        <head><base href="http://www.example.com/img/" target="_blank"></head>
        <body>blahablsdfsal&amp;</body>
        </html>""")
        self.assertEqual(get_base_url(resp), "http://www.example.com/img/")

        resp2 = HtmlResponse("http://www.example.com", body=b"""
        <html><body>blahablsdfsal&amp;</body></html>""")
        self.assertEqual(get_base_url(resp2), "http://www.example.com")

    def test_response_status_message(self):
        self.assertEqual(response_status_message(200), '200 OK')
        self.assertEqual(response_status_message(404), '404 Not Found')
        self.assertEqual(response_status_message(573), "573 Unknown Status")
