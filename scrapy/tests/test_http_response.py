import unittest
import weakref

from scrapy.http import Response, TextResponse, HtmlResponse, XmlResponse, Headers
from scrapy.conf import settings


class BaseResponseTest(unittest.TestCase):

    response_class = Response

    def test_init(self):
        # Response requires url in the consturctor
        self.assertRaises(Exception, self.response_class)
        self.assertTrue(isinstance(self.response_class('http://example.com/'), self.response_class))
        # body can be str or None
        self.assertTrue(isinstance(self.response_class('http://example.com/', body=''), self.response_class))
        self.assertTrue(isinstance(self.response_class('http://example.com/', body='body'), self.response_class))
        # test presence of all optional parameters
        self.assertTrue(isinstance(self.response_class('http://example.com/', headers={}, status=200, body=''), self.response_class))

        r = self.response_class("http://www.example.com")
        assert isinstance(r.url, str)
        self.assertEqual(r.url, "http://www.example.com")
        self.assertEqual(r.status, 200)

        assert isinstance(r.headers, Headers)
        self.assertEqual(r.headers, {})
        self.assertEqual(r.meta, {})

        meta = {"lala": "lolo"}
        headers = {"caca": "coco"}
        body = "a body"
        r = self.response_class("http://www.example.com", meta=meta, headers=headers, body=body)

        assert r.meta is not meta
        self.assertEqual(r.meta, meta)
        assert r.headers is not headers
        self.assertEqual(r.headers["caca"], "coco")

        r = self.response_class("http://www.example.com", status=301)
        self.assertEqual(r.status, 301)
        r = self.response_class("http://www.example.com", status='301')
        self.assertEqual(r.status, 301)
        self.assertRaises(ValueError, self.response_class, "http://example.com", status='lala200')

    def test_copy(self):
        """Test Response copy"""

        r1 = self.response_class("http://www.example.com", body="Some body")
        r1.meta['foo'] = 'bar'
        r1.flags.append('cached')
        r2 = r1.copy()

        self.assertEqual(r1.status, r2.status)
        self.assertEqual(r1.body, r2.body)

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

        class CustomResponse(self.response_class):
            pass

        r1 = CustomResponse('http://www.example.com')
        r2 = r1.copy()

        assert type(r2) is CustomResponse

    def test_replace(self):
        """Test Response.replace() method"""
        hdrs = Headers({"key": "value"})
        r1 = self.response_class("http://www.example.com")
        r2 = r1.replace(status=301, body="New body", headers=hdrs)
        assert r1.body == ''
        self.assertEqual(r1.url, r2.url)
        self.assertEqual((r1.status, r2.status), (200, 301))
        self.assertEqual((r1.body, r2.body), ('', "New body"))
        self.assertEqual((r1.headers, r2.headers), ({}, hdrs))

        # Empty attributes (which may fail if not compared properly)
        r3 = self.response_class("http://www.example.com", meta={'a': 1}, flags=['cached'])
        r4 = r3.replace(body='', meta={}, flags=[])
        self.assertEqual(r4.body, '')
        self.assertEqual(r4.meta, {})
        self.assertEqual(r4.flags, [])

    def test_weakref_slots(self):
        """Check that classes are using slots and are weak-referenceable"""
        x = self.response_class('http://www.example.com')
        weakref.ref(x)
        assert not hasattr(x, '__dict__'), "%s does not use __slots__" % \
            x.__class__.__name__

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

class ResponseText(BaseResponseTest):

    def test_no_unicode_url(self):
        self.assertRaises(TypeError, self.response_class, u'http://www.example.com')
    

class TextResponseTest(BaseResponseTest):

    response_class = TextResponse

    def test_replace(self):
        super(TextResponseTest, self).test_replace()
        r1 = self.response_class("http://www.example.com", body="hello", encoding="cp852")
        r2 = r1.replace(url="http://www.example.com/other")
        r3 = r1.replace(url="http://www.example.com/other", encoding="latin1")

        assert isinstance(r2, self.response_class)
        self.assertEqual(r2.url, "http://www.example.com/other")
        self.assertEqual(r2.encoding, "cp852")
        self.assertEqual(r3.url, "http://www.example.com/other")
        self.assertEqual(r3.encoding, "latin1")

    def test_unicode_url(self):
        # instantiate with unicode url without encoding (should set default encoding)
        resp = self.response_class(u"http://www.example.com/")
        self.assertEqual(resp.encoding, settings['DEFAULT_RESPONSE_ENCODING'])

        # make sure urls are converted to str
        resp = self.response_class(url=u"http://www.example.com/", encoding='utf-8')
        assert isinstance(resp.url, str)

        resp = self.response_class(url=u"http://www.example.com/price/\xa3", encoding='utf-8')
        self.assertEqual(resp.url, 'http://www.example.com/price/\xc2\xa3')
        resp = self.response_class(url=u"http://www.example.com/price/\xa3", encoding='latin-1')
        self.assertEqual(resp.url, 'http://www.example.com/price/\xa3')
        resp = self.response_class(url="http://www.example.com/price/", encoding='utf-8')
        resp.url = u'http://www.example.com/price/\xa3'
        self.assertEqual(resp.url, 'http://www.example.com/price/\xc2\xa3')
        resp = self.response_class(u"http://www.example.com/price/\xa3", headers={"Content-type": ["text/html; charset=utf-8"]})
        self.assertEqual(resp.url, 'http://www.example.com/price/\xc2\xa3')
        resp = self.response_class(u"http://www.example.com/price/\xa3", headers={"Content-type": ["text/html; charset=iso-8859-1"]})
        self.assertEqual(resp.url, 'http://www.example.com/price/\xa3')

    def test_unicode_body(self):
        unicode_string = u'\u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0442\u0435\u043a\u0441\u0442'
        self.assertRaises(TypeError, self.response_class, 'http://www.example.com', body=u'unicode body')

        original_string = unicode_string.encode('cp1251')
        r1 = self.response_class('http://www.example.com', body=original_string, encoding='cp1251')

        # check body_as_unicode
        self.assertTrue(isinstance(r1.body_as_unicode(), unicode))
        self.assertEqual(r1.body_as_unicode(), unicode_string)

    def test_encoding(self):
        r1 = self.response_class("http://www.example.com", headers={"Content-type": ["text/html; charset=utf-8"]}, body="\xc2\xa3")
        r2 = self.response_class("http://www.example.com", encoding='utf-8', body=u"\xa3")
        r3 = self.response_class("http://www.example.com", headers={"Content-type": ["text/html; charset=iso-8859-1"]}, body="\xa3")
        r4 = self.response_class("http://www.example.com", body="\xa2\xa3")
        r5 = self.response_class("http://www.example.com",
        headers={"Content-type": ["text/html; charset=None"]}, body="\xc2\xa3")

        self.assertEqual(r1.headers_encoding(), "utf-8")
        self.assertEqual(r2.headers_encoding(), None)
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertEqual(r3.headers_encoding(), "iso-8859-1")
        self.assertEqual(r3.encoding, 'iso-8859-1')
        self.assertEqual(r4.headers_encoding(), None)
        self.assertEqual(r5.headers_encoding(), None)
        self.assertEqual(r5.encoding, "utf-8")
        assert r4.body_encoding() is not None and r4.body_encoding() != 'ascii'
        self._assert_response_values(r1, 'utf-8', u"\xa3")
        self._assert_response_values(r2, 'utf-8', u"\xa3")
        self._assert_response_values(r3, 'iso-8859-1', u"\xa3")

        # TextResponse (and subclasses) must be passed a encoding when instantiating with unicode bodies
        self.assertRaises(TypeError, self.response_class, "http://www.example.com", body=u"\xa3")

class HtmlResponseTest(TextResponseTest):

    response_class = HtmlResponse

    def test_html_encoding(self):
        
        body = """<html><head><title>Some page</title><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
        </head><body>Price: \xa3100</body></html>'
        """
        r1 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r1, 'iso-8859-1', body)

        body = """<?xml version="1.0" encoding="iso-8859-1"?>
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
        Price: \xa3100
        """
        r2 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r2, 'iso-8859-1', body)

        # for conflicting declarations headers must take precedence
        body = """<html><head><title>Some page</title><meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        </head><body>Price: \xa3100</body></html>'
        """
        r3 = self.response_class("http://www.example.com", headers={"Content-type": ["text/html; charset=iso-8859-1"]}, body=body)
        self._assert_response_values(r3, 'iso-8859-1', body)

        # make sure replace() preserves the encoding of the original response
        body = "New body \xa3"
        r4 = r3.replace(body=body)
        self._assert_response_values(r4, 'iso-8859-1', body)



class XmlResponseTest(TextResponseTest):

    response_class = XmlResponse

    def test_xml_encoding(self):

        body = "<xml></xml>"
        r1 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r1, settings['DEFAULT_RESPONSE_ENCODING'], body)

        body = """<?xml version="1.0" encoding="iso-8859-1"?><xml></xml>"""
        r2 = self.response_class("http://www.example.com", body=body)
        self._assert_response_values(r2, 'iso-8859-1', body)

        # make sure replace() preserves the explicit encoding passed in the constructor
        body = """<?xml version="1.0" encoding="iso-8859-1"?><xml></xml>"""
        r3 = self.response_class("http://www.example.com", body=body, encoding='utf-8')
        body2 = "New body"
        r4 = r3.replace(body=body2)
        self._assert_response_values(r4, 'utf-8', body2)

        # make sure replace() rediscovers the encoding (if not given explicitly) when changing the body
        body = """<?xml version="1.0" encoding="iso-8859-1"?><xml></xml>"""
        r5 = self.response_class("http://www.example.com", body=body)
        body2 = """<?xml version="1.0" encoding="utf-8"?><xml></xml>"""
        r6 = r5.replace(body=body2)
        self._assert_response_values(r5, 'iso-8859-1', body)
        self._assert_response_values(r6, 'utf-8', body2)


if __name__ == "__main__":
    unittest.main()
