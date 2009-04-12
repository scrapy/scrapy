import unittest
from cStringIO import StringIO
import cgi

from scrapy.http import Request, FormRequest, XmlRpcRequest, Headers, Url, Response

class RequestTest(unittest.TestCase):

    def test_init(self):
        # Request requires url in the constructor
        self.assertRaises(Exception, Request)

        # url argument must be basestring or Url
        self.assertRaises(TypeError, Request, 123)
        r = Request(Url('http://www.example.com'))

        r = Request("http://www.example.com")
        assert isinstance(r.url, Url)
        self.assertEqual(r.url, "http://www.example.com")
        self.assertEqual(r.method, "GET")

        r.url = "http://www.example.com/other"
        assert isinstance(r.url, Url)

        assert isinstance(r.headers, Headers)
        self.assertEqual(r.headers, {})
        self.assertEqual(r.meta, {})

        meta = {"lala": "lolo"}
        headers = {"caca": "coco"}
        body = "a body"
        r = Request("http://www.example.com", meta=meta, headers=headers, body="a body")

        assert r.meta is not meta
        self.assertEqual(r.meta, meta)
        assert r.headers is not headers
        self.assertEqual(r.headers["caca"], "coco")

    def test_headers(self):
        # Different ways of setting headers attribute
        url = 'http://www.scrapy.org'
        headers = {'Accept':'gzip', 'Custom-Header':'nothing to tell you'}
        r = Request(url=url, headers=headers)
        p = Request(url=url, headers=r.headers)

        self.assertEqual(r.headers, p.headers)
        self.assertFalse(r.headers is headers)
        self.assertFalse(p.headers is r.headers)

        # headers must not be unicode
        h = Headers({'key1': u'val1', u'key2': 'val2'})
        h[u'newkey'] = u'newval'
        for k, v in h.iteritems():
            self.assert_(isinstance(k, str))
            self.assert_(isinstance(v, str))

    def test_eq(self):
        url = 'http://www.scrapy.org'
        r1 = Request(url=url)
        r2 = Request(url=url)
        self.assertNotEqual(r1, r2)

        set_ = set()
        set_.add(r1)
        set_.add(r2)
        self.assertEqual(len(set_), 2)

    def test_url(self):
        """Request url tests"""
        r = Request(url="http://www.scrapy.org/path")
        self.assertEqual(r.url, "http://www.scrapy.org/path")

        # url quoting on attribute assign
        r.url = "http://www.scrapy.org/blank%20space"
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")
        r.url = "http://www.scrapy.org/blank space"
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")

        # url quoting on creation
        r = Request(url="http://www.scrapy.org/blank%20space")
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")
        r = Request(url="http://www.scrapy.org/blank space")
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")

        # url coercion to string
        r.url = u"http://www.scrapy.org/test"
        self.assert_(isinstance(r.url, str))

        # url encoding
        r1 = Request(url=u"http://www.scrapy.org/price/\xa3", encoding="utf-8")
        r2 = Request(url=u"http://www.scrapy.org/price/\xa3", encoding="latin1")
        self.assertEqual(r1.url, "http://www.scrapy.org/price/%C2%A3")
        self.assertEqual(r2.url, "http://www.scrapy.org/price/%A3")

    def test_body(self):
        r1 = Request(url="http://www.example.com/")
        assert r1.body == ''

        r2 = Request(url="http://www.example.com/", body="")
        assert isinstance(r2.body, str)
        self.assertEqual(r2.encoding, 'utf-8') # default encoding

        r3 = Request(url="http://www.example.com/", body=u"Price: \xa3100", encoding='utf-8')
        assert isinstance(r3.body, str)
        self.assertEqual(r3.body, "Price: \xc2\xa3100")

        r4 = Request(url="http://www.example.com/", body=u"Price: \xa3100", encoding='latin1')
        assert isinstance(r4.body, str)
        self.assertEqual(r4.body, "Price: \xa3100")

    def test_copy(self):
        """Test Request copy"""
        
        def somecallback():
            pass

        r1 = Request("http://www.example.com", callback=somecallback)
        r1.meta['foo'] = 'bar'
        r1.cache['lala'] = 'lolo'
        r2 = r1.copy()

        assert r1.cache
        assert not r2.cache

        assert r1.deferred is not r2.deferred

        # make sure meta dict is shallow copied
        assert r1.meta is not r2.meta, "meta must be a shallow copy, not identical"
        self.assertEqual(r1.meta, r2.meta)

        # make sure headers attribute is shallow copied
        assert r1.headers is not r2.headers, "headers must be a shallow copy, not identical"
        self.assertEqual(r1.headers, r2.headers)
        self.assertEqual(r1.encoding, r2.encoding)
        self.assertEqual(r1.dont_filter, r2.dont_filter)

        # Request.body can be identical since it's an immutable object (str)

    def test_copy_inherited_classes(self):
        """Test Request children copies preserve their class"""

        class CustomRequest(Request):
            pass

        r1 = CustomRequest('example.com', 'http://www.example.com')
        r2 = r1.copy()

        assert type(r2) is CustomRequest

    def test_replace(self):
        """Test Request.replace() method"""
        hdrs = Headers({"key": "value"})
        r1 = Request("http://www.example.com")
        r2 = r1.replace(method="POST", body="New body", headers=hdrs)
        self.assertEqual(r1.url, r2.url)
        self.assertEqual((r1.method, r2.method), ("GET", "POST"))
        self.assertEqual((r1.body, r2.body), ('', "New body"))
        self.assertEqual((r1.headers, r2.headers), ({}, hdrs))

        # Empty attributes (which may fail if not compared properly)
        r3 = Request("http://www.example.com", meta={'a': 1}, dont_filter=True)
        r4 = r3.replace(url="http://www.example.com/2", body='', meta={}, dont_filter=False)
        self.assertEqual(r4.url, "http://www.example.com/2")
        self.assertEqual(r4.body, '')
        self.assertEqual(r4.meta, {})
        assert r4.dont_filter is False

    def test_httprepr(self):
        r1 = Request("http://www.example.com")
        self.assertEqual(r1.httprepr(), 'GET http://www.example.com HTTP/1.1\r\nHost: www.example.com\r\n\r\n')

        r1 = Request("http://www.example.com", method='POST', headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(r1.httprepr(), 'POST http://www.example.com HTTP/1.1\r\nHost: www.example.com\r\nContent-Type: text/html\r\n\r\nSome body')


class FormRequestTest(unittest.TestCase):

    def test_empty_formdata(self):
        r1 = FormRequest("http://www.example.com", formdata={})
        self.assertEqual(r1.body, '')

    def test_default_encoding(self):
        # using default encoding (utf-8)
        data = {'one': 'two', 'price': '\xc2\xa3 100'}
        r2 = FormRequest("http://www.example.com", formdata=data)
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertEqual(r2.body, 'price=%C2%A3+100&one=two')
        self.assertEqual(r2.headers['Content-Type'], 'application/x-www-form-urlencoded')

    def test_custom_encoding(self):
        data = {'price': u'\xa3 100'}
        r3 = FormRequest("http://www.example.com", formdata=data, encoding='latin1')
        self.assertEqual(r3.encoding, 'latin1')
        self.assertEqual(r3.body, 'price=%A3+100')

    def test_multi_key_values(self):
        # using multiples values for a single key
        data = {'price': u'\xa3 100', 'colours': ['red', 'blue', 'green']}
        r3 = FormRequest("http://www.example.com", formdata=data)
        self.assertEqual(r3.body, 'colours=red&colours=blue&colours=green&price=%C2%A3+100')

    def test_from_response_post(self):
        respbody = """
<form action="post.php" method="POST">
<input type="hidden" name="test" value="val1">
<input type="hidden" name="test" value="val2">
<input type="hidden" name="test2" value="xxx">
</form>
        """
        response = Response("http://www.example.com/this/list.html", body=respbody)
        r1 = FormRequest.from_response(response, formdata={'one': ['two', 'three'], 'six': 'seven'}, callback=lambda x: x)
        fs = cgi.FieldStorage(StringIO(r1.body), r1.headers, environ={"REQUEST_METHOD": "POST"})
        self.assertEqual(r1.url, "http://www.example.com/this/post.php")
        self.assertEqual(set([f.value for f in fs["test"]]), set(["val1", "val2"]))
        self.assertEqual(set([f.value for f in fs["one"]]), set(["two", "three"]))
        self.assertEqual(fs['test2'].value, 'xxx')
        self.assertEqual(fs['six'].value, 'seven')

    def test_from_response_get(self):
        respbody = """
<form action="get.php" method="GET">
<input type="hidden" name="test" value="val1">
<input type="hidden" name="test" value="val2">
<input type="hidden" name="test2" value="xxx">
</form>
        """
        response = Response("http://www.example.com/this/list.html", body=respbody)
        r1 = FormRequest.from_response(response, formdata={'one': ['two', 'three'], 'six': 'seven'})
        self.assertEqual(r1.url.hostname, "www.example.com")
        self.assertEqual(r1.url.path, "/this/get.php")
        urlargs = cgi.parse_qs(r1.url.query)
        self.assertEqual(set(urlargs['test']), set(['val1', 'val2']))
        self.assertEqual(set(urlargs['one']), set(['two', 'three']))
        self.assertEqual(urlargs['test2'], ['xxx'])
        self.assertEqual(urlargs['six'], ['seven'])

    def test_from_response_errors_noform(self):
        respbody = """<html></html>"""
        response = Response("http://www.example.com/lala.html", body=respbody)
        self.assertRaises(ValueError, FormRequest.from_response, response)

    def test_from_response_errors_formnumber(self):
        respbody = """
<form action="get.php" method="GET">
<input type="hidden" name="test" value="val1">
<input type="hidden" name="test" value="val2">
<input type="hidden" name="test2" value="xxx">
</form>
        """
        response = Response("http://www.example.com/lala.html", body=respbody)
        self.assertRaises(IndexError, FormRequest.from_response, response, formnumber=1)

class XmlRpcRequestTest(unittest.TestCase):

    def test_basic(self):
        r = XmlRpcRequest('http://scrapytest.org/rpc2', methodname='login', params=('username', 'password'))
        self.assertEqual(r.headers['Content-Type'], 'text/xml')
        self.assertEqual(r.body, "<?xml version='1.0'?>\n<methodCall>\n<methodName>login</methodName>\n<params>\n<param>\n<value><string>username</string></value>\n</param>\n<param>\n<value><string>password</string></value>\n</param>\n</params>\n</methodCall>\n")
        self.assertEqual(r.method, 'POST')
        self.assertTrue(r.dont_filter, True)


if __name__ == "__main__":
    unittest.main()
