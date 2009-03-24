import unittest
from scrapy.http import Response, TextResponse, HtmlResponse, XmlResponse, Headers, Url

class ResponseTest(unittest.TestCase):

    def test_init(self):
        # Response requires url in the consturctor
        self.assertRaises(Exception, Response)
        self.assertTrue(isinstance(Response('http://example.com/'), Response))
        # body can be str or None but not ResponseBody
        self.assertTrue(isinstance(Response('http://example.com/', body=''), Response))
        self.assertTrue(isinstance(Response('http://example.com/', body='body'), Response))
        # test presence of all optional parameters
        self.assertTrue(isinstance(Response('http://example.com/', headers={}, status=200, body=''), Response))

        r = Response("http://www.example.com")
        assert isinstance(r.url, Url)
        self.assertEqual(r.url, "http://www.example.com")
        self.assertEqual(r.status, 200)

        assert isinstance(r.headers, Headers)
        self.assertEqual(r.headers, {})
        self.assertEqual(r.meta, {})

        meta = {"lala": "lolo"}
        headers = {"caca": "coco"}
        body = "a body"
        r = Response("http://www.example.com", meta=meta, headers=headers, body="a body")

        assert r.meta is not meta
        self.assertEqual(r.meta, meta)
        assert r.headers is not headers
        self.assertEqual(r.headers["caca"], "coco")

        r = Response("http://www.example.com", status=301)
        self.assertEqual(r.status, 301)
        r = Response("http://www.example.com", status='301')
        self.assertEqual(r.status, 301)
        self.assertRaises(ValueError, Response, "http://example.com", status='lala200')

    def test_copy(self):
        """Test Response copy"""

        r1 = Response("http://www.example.com", body="Some body")
        r1.meta['foo'] = 'bar'
        r1.flags.append('cached')
        r1.cache['lala'] = 'lolo'
        r2 = r1.copy()

        self.assertEqual(r1.status, r2.status)
        self.assertEqual(r1.body, r2.body)

        assert r1.cache
        assert not r2.cache

        # make sure meta dict is shallow copied
        assert r1.meta is not r2.meta, "meta must be a shallow copy, not identical"
        self.assertEqual(r1.meta, r2.meta)

        # make sure flags list is shallow copied
        assert r1.flags is not r2.flags, "flags must be a shallow copy, not identical"
        self.assertEqual(r1.flags, r2.flags)

        # make sure headers attribute is shallow copied
        assert r1.headers is not r2.headers, "headers must be a shallow copy, not identical"
        self.assertEqual(r1.headers, r2.headers)

    def test_copy_inherited_classes(self):
        """Test Response children copies preserve their class"""

        class CustomResponse(Response):
            pass

        r1 = CustomResponse('http://www.example.com')
        r2 = r1.copy()

        assert type(r2) is CustomResponse

    def test_replace(self):
        """Test Response.replace() method"""
        hdrs = Headers({"key": "value"})
        r1 = Response("http://www.example.com")
        r2 = r1.replace(status=301, body="New body", headers=hdrs)
        assert r1.body == ''
        self.assertEqual(r1.url, r2.url)
        self.assertEqual((r1.status, r2.status), (200, 301))
        self.assertEqual((r1.body, r2.body), ('', "New body"))
        self.assertEqual((r1.headers, r2.headers), ({}, hdrs))

        r1 = TextResponse("http://www.example.com", body="hello", encoding="cp852")
        r2 = r1.replace(url="http://www.example.com/other")
        r3 = r1.replace(url="http://www.example.com/other", encoding="latin1")

        assert isinstance(r2, TextResponse)
        self.assertEqual(r2.url, "http://www.example.com/other")
        self.assertEqual(r2.encoding, "cp852")
        self.assertEqual(r3.url, "http://www.example.com/other")
        self.assertEqual(r3.encoding, "latin1")

        # Empty attributes (which may fail if not compared properly)
        r3 = Response("http://www.example.com", meta={'a': 1}, flags=['cached'])
        r4 = r3.replace(body='', meta={}, flags=[])
        self.assertEqual(r4.body, '')
        self.assertEqual(r4.meta, {})
        self.assertEqual(r4.flags, [])

    def test_httprepr(self):
        r1 = Response("http://www.example.com")
        self.assertEqual(r1.httprepr(), 'HTTP/1.1 200 OK\r\n\r\n')

        r1 = Response("http://www.example.com", status=404, headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(r1.httprepr(), 'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\nSome body')

    def test_encoding(self):
        unicode_string = u'\u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0442\u0435\u043a\u0441\u0442'
        self.assertRaises(TypeError, Response, 'http://www.example.com', body=u'unicode body')

        original_string = unicode_string.encode('cp1251')
        r1 = TextResponse('http://www.example.com', body=original_string, encoding='cp1251')

        # check body_as_unicode
        self.assertTrue(isinstance(r1.body_as_unicode(), unicode))
        self.assertEqual(r1.body_as_unicode(), unicode_string)

    def _assert_response_values(self, response, encoding, body):
        if isinstance(body, unicode):
            body_unicode = body
            body_str = body.encode(encoding)
        else:
            body_unicode = body.decode(encoding)
            body_str = body

        assert isinstance(response.body, str)
        self.assertEqual(response.encoding, encoding)
        self.assertEqual(response.body, body_str)
        self.assertEqual(response.body_as_unicode(), body_unicode)

    def test_text_response(self):
        r1 = TextResponse("http://www.example.com", headers={"Content-type": ["text/html; charset=utf-8"]}, body="\xc2\xa3")
        r2 = TextResponse("http://www.example.com", encoding='utf-8', body=u"\xa3")
        r3 = TextResponse("http://www.example.com", headers={"Content-type": ["text/html; charset=iso-8859-1"]}, body="\xa3")
        r4 = TextResponse("http://www.example.com", body="\xa2\xa3")

        self.assertEqual(r1.headers_encoding(), "utf-8")
        self.assertEqual(r2.headers_encoding(), None)
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertEqual(r3.headers_encoding(), "iso-8859-1")
        self.assertEqual(r3.encoding, 'iso-8859-1')
        self.assertEqual(r4.headers_encoding(), None)
        assert r4.body_encoding() is not None and r4.body_encoding() != 'ascii'
        self._assert_response_values(r1, 'utf-8', u"\xa3")
        self._assert_response_values(r2, 'utf-8', u"\xa3")
        self._assert_response_values(r3, 'iso-8859-1', u"\xa3")

        # TextResponse (and subclasses) must be passed a encoding when instantiating with unicode bodies
        self.assertRaises(TypeError, TextResponse, "http://www.example.com", body=u"\xa3")

    def test_html_encoding(self):
        
        body = """<html><head><title>Some page</title><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
        </head><body>Price: \xa3100</body></html>'
        """
        r1 = HtmlResponse("http://www.example.com", body=body)
        self._assert_response_values(r1, 'iso-8859-1', body)

        body = """<?xml version="1.0" encoding="iso-8859-1"?>
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
        Price: \xa3100
        """
        r2 = HtmlResponse("http://www.example.com", body=body)
        self._assert_response_values(r2, 'iso-8859-1', body)

        # for conflicting declarations headers must take precedence
        body = """<html><head><title>Some page</title><meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        </head><body>Price: \xa3100</body></html>'
        """
        r3 = HtmlResponse("http://www.example.com", headers={"Content-type": ["text/html; charset=iso-8859-1"]}, body=body)
        self._assert_response_values(r3, 'iso-8859-1', body)

        # make sure replace() preserves the encoding of the original response
        body = "New body \xa3"
        r4 = r3.replace(body=body)
        self._assert_response_values(r4, 'iso-8859-1', body)

    def test_xml_encoding(self):

        body = "<xml></xml>"
        r1 = XmlResponse("http://www.example.com", body=body)
        # XXX: we may want to swtich default XmlResponse encoding to utf-8
        self._assert_response_values(r1, 'ascii', body)

        body = """<?xml version="1.0" encoding="iso-8859-1"?><xml></xml>"""
        r2 = XmlResponse("http://www.example.com", body=body)
        self._assert_response_values(r2, 'iso-8859-1', body)

        # make sure replace() preserves the encoding of the original response
        body = "New body \xa3"
        r3 = r2.replace(body=body)
        self._assert_response_values(r3, 'iso-8859-1', body)


if __name__ == "__main__":
    unittest.main()
