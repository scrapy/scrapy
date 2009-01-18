import unittest
from scrapy.http import Response, Headers, Url
from scrapy.http.response import _ResponseBody

class ResponseTest(unittest.TestCase):

    def test_init(self):
        # Response requires url in the consturctor
        self.assertRaises(Exception, Response)
        self.assertTrue(isinstance(Response('http://example.com/'), Response))
        # body can be str or None but not ResponseBody
        self.assertTrue(isinstance(Response('http://example.com/', body=None), Response))
        self.assertTrue(isinstance(Response('http://example.com/', body='body'), Response))
        # test presence of all optional parameters
        self.assertTrue(isinstance(Response('http://example.com/', headers={}, status=200, body=None), Response))

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

    def test_copy(self):
        """Test Response copy"""
        
        r1 = Response("http://www.example.com")
        r1.meta['foo'] = 'bar'
        r1.cache['lala'] = 'lolo'
        r2 = r1.copy()

        assert r1.cache
        assert not r2.cache

        # make sure meta dict is shallow copied
        assert r1.meta is not r2.meta, "meta must be a shallow copy, not identical"
        self.assertEqual(r1.meta, r2.meta)

    def test_copy_inherited_classes(self):
        """Test Response children copies preserve their class"""

        class CustomResponse(Response):
            pass

        r1 = CustomResponse('http://www.example.com')
        r2 = r1.copy()

        assert type(r2) is CustomResponse

    def test_httprepr(self):
        r1 = Response("http://www.example.com")
        self.assertEqual(r1.httprepr(), 'HTTP/1.1 200 OK\r\n\r\n')

        r1 = Response("http://www.example.com", status=404, headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(r1.httprepr(), 'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\nSome body\r\n')
        
class ResponseBodyTest(unittest.TestCase):
    unicode_string = u'\u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0442\u0435\u043a\u0441\u0442'

    def test_encoding(self):
        original_string = self.unicode_string.encode('cp1251')
        cp1251_body     = _ResponseBody(original_string, 'cp1251')

        # check to_unicode
        self.assertTrue(isinstance(cp1251_body.to_unicode(), unicode))
        self.assertEqual(cp1251_body.to_unicode(), self.unicode_string)

        # check to_string using default encoding (declared when created)
        self.assertTrue(isinstance(cp1251_body.to_string(), str))
        self.assertEqual(cp1251_body.to_string(), original_string)

        # check to_string using arbitrary encoding
        self.assertTrue(isinstance(cp1251_body.to_string('utf-8'), str))
        self.assertEqual(cp1251_body.to_string('utf-8'), self.unicode_string.encode('utf-8'))

if __name__ == "__main__":
    unittest.main()
