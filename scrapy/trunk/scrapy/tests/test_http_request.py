import unittest
from scrapy.http import Request, FormRequest, Headers, Url

class RequestTest(unittest.TestCase):

    def test_init(self):
        # Request requires url in the constructor
        self.assertRaises(Exception, Request)

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

    def test_httprepr(self):
        r1 = Request("http://www.example.com")
        self.assertEqual(r1.httprepr(), 'GET http://www.example.com HTTP/1.1\r\nHost: www.example.com\r\n\r\n')

        r1 = Request("http://www.example.com", method='POST', headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(r1.httprepr(), 'POST http://www.example.com HTTP/1.1\r\nHost: www.example.com\r\nContent-Type: text/html\r\n\r\nSome body')

    def test_form_request(self):

        # empty formdata
        r1 = FormRequest("http://www.example.com", formdata={})
        self.assertEqual(r1.body, '')

        # using default encoding (utf-8)
        data = {'one': 'two', 'price': '\xc2\xa3 100'}
        r2 = FormRequest("http://www.example.com", formdata=data)
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertEqual(r2.body, 'price=%C2%A3+100&one=two')
        self.assertEqual(r2.headers['Content-Type'], 'application/x-www-form-urlencoded')

        # using custom encoding
        data = {'price': u'\xa3 100'}
        r3 = FormRequest("http://www.example.com", formdata=data, encoding='latin1')
        self.assertEqual(r3.encoding, 'latin1')
        self.assertEqual(r3.body, 'price=%A3+100')

        # using multiples values for a single key
        data = {'price': u'\xa3 100', 'colours': ['red', 'blue', 'green']}
        r3 = FormRequest("http://www.example.com", formdata=data)
        self.assertEqual(r3.body, 'colours=red&colours=blue&colours=green&price=%C2%A3+100')

if __name__ == "__main__":
    unittest.main()
