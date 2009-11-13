import unittest

from scrapy.xlib.BeautifulSoup import BeautifulSoup
from scrapy.http import Response, TextResponse
from scrapy.utils.response import body_or_str, get_base_url, get_meta_refresh, \
    response_httprepr, get_cached_beautifulsoup

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

    def test_get_base_url(self):
        response = Response(url='http://example.org', body="""\
            <html>\
            <head><title>Dummy</title><base href='http://example.org/something' /></head>\
            <body>blahablsdfsal&amp;</body>\
            </html>""")
        self.assertEqual(get_base_url(response), 'http://example.org/something')

    def test_get_meta_refresh(self):
        body = """
            <html>
            <head><title>Dummy</title><meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
            <body>blahablsdfsal&amp;</body>
            </html>"""
        response = Response(url='http://example.org', body=body)
        self.assertEqual(get_meta_refresh(response), (5, 'http://example.org/newpage'))

        # refresh without url should return (None, None)
        body = """<meta http-equiv="refresh" content="5" />"""
        response = Response(url='http://example.org', body=body)
        self.assertEqual(get_meta_refresh(response), (None, None))

        body = """<meta http-equiv="refresh" content="5;
            url=http://example.org/newpage" /></head>"""
        response = Response(url='http://example.org', body=body)
        self.assertEqual(get_meta_refresh(response), (5, 'http://example.org/newpage'))

        # meta refresh in multiple lines
        body = """<html><head>
               <META
               HTTP-EQUIV="Refresh"
               CONTENT="1; URL=http://example.org/newpage">"""
        response = Response(url='http://example.org', body=body)
        self.assertEqual(get_meta_refresh(response), (1, 'http://example.org/newpage'))

        # entities in the redirect url
        body = """<meta http-equiv="refresh" content="3; url=&#39;http://www.example.com/other&#39;">"""
        response = Response(url='http://example.com', body=body)
        self.assertEqual(get_meta_refresh(response), (3, 'http://www.example.com/other'))

        # relative redirects
        body = """<meta http-equiv="refresh" content="3; url=other.html">"""
        response = Response(url='http://example.com/page/this.html', body=body)
        self.assertEqual(get_meta_refresh(response), (3, 'http://example.com/page/other.html'))

        # non-standard encodings (utf-16)
        body = """<meta http-equiv="refresh" content="3; url=http://example.com/redirect">"""
        body = body.decode('ascii').encode('utf-16')
        response = TextResponse(url='http://example.com', body=body, encoding='utf-16')
        self.assertEqual(get_meta_refresh(response), (3, 'http://example.com/redirect'))

        # non-ascii chars in the url (default encoding - utf8)
        body = """<meta http-equiv="refresh" content="3; url=http://example.com/to\xc2\xa3">"""
        response = Response(url='http://example.com', body=body)
        self.assertEqual(get_meta_refresh(response), (3, 'http://example.com/to%C2%A3'))

        # non-ascii chars in the url (custom encoding - latin1)
        body = """<meta http-equiv="refresh" content="3; url=http://example.com/to\xa3">"""
        response = TextResponse(url='http://example.com', body=body, encoding='latin1')
        self.assertEqual(get_meta_refresh(response), (3, 'http://example.com/to%C2%A3'))

        # wrong encodings (possibly caused by truncated chunks)
        body = """<meta http-equiv="refresh" content="3; url=http://example.com/this\xc2_THAT">"""
        response = Response(url='http://example.com', body=body)
        self.assertEqual(get_meta_refresh(response), (3, 'http://example.com/thisTHAT'))

        # responses without refresh tag should return None None
        response = Response(url='http://example.org')
        self.assertEqual(get_meta_refresh(response), (None, None))
        response = TextResponse(url='http://example.org')
        self.assertEqual(get_meta_refresh(response), (None, None))

    def test_response_httprepr(self):
        r1 = Response("http://www.example.com")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 200 OK\r\n\r\n')

        r1 = Response("http://www.example.com", status=404, headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(response_httprepr(r1), 'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\nSome body')

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

if __name__ == "__main__":
    unittest.main()
