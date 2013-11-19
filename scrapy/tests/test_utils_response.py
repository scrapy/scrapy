import os
import unittest
import urlparse

from scrapy.http import Response, TextResponse, HtmlResponse
from scrapy.utils.response import response_httprepr, open_in_browser, get_meta_refresh

__doctests__ = ['scrapy.utils.response']

class ResponseUtilsTest(unittest.TestCase):
    dummy_response = TextResponse(url='http://example.org/', body='dummy_response')

    def test_response_httprepr(self):
        r1 = Response("http://www.example.com")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 200 OK\r\n\r\n')

        r1 = Response("http://www.example.com", status=404, headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\nSome body')

        r1 = Response("http://www.example.com", status=6666, headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 6666 \r\nContent-Type: text/html\r\n\r\nSome body')

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

    def test_get_meta_refresh(self):
        r1 = HtmlResponse("http://www.example.com", body="""
        <html>
        <head><title>Dummy</title><meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        <body>blahablsdfsal&amp;</body>
        </html>""")
        r2 = HtmlResponse("http://www.example.com", body="""
        <html>
        <head><title>Dummy</title><noScript>
        <meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        </noSCRIPT>
        <body>blahablsdfsal&amp;</body>
        </html>""")
        r3 = HtmlResponse("http://www.example.com", body="""
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

if __name__ == "__main__":
    unittest.main()
