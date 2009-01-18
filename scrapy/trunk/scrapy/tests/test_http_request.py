import unittest
from scrapy.http import Request, Headers, Url
from scrapy.core.scheduler import GroupFilter

class RequestTest(unittest.TestCase):

    def test_init(self):
        # Request requires url in the constructor
        self.assertRaises(Exception, Request)

        r = Request("http://www.example.com")
        assert isinstance(r.url, Url)
        self.assertEqual(r.url, "http://www.example.com")
        self.assertEqual(r.method, "GET")

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

    def test_groupfilter(self):
        k1 = "id1"
        k2 = "id1"

        f = GroupFilter()
        f.open("mygroup")
        self.assertTrue(f.add("mygroup", k1))
        self.assertFalse(f.add("mygroup", k1))
        self.assertFalse(f.add("mygroup", k2))

        f.open('anothergroup')
        self.assertTrue(f.add("anothergroup", k1))
        self.assertFalse(f.add("anothergroup", k1))
        self.assertFalse(f.add("anothergroup", k2))

        f.close('mygroup')
        f.open('mygroup')
        self.assertTrue(f.add("mygroup", k2))
        self.assertFalse(f.add("mygroup", k1))

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
        r = Request(url=u"http://www.scrapy.org/price/\xa3", url_encoding="utf-8")
        self.assert_(isinstance(r.url, str))
        self.assertEqual(r.url, "http://www.scrapy.org/price/%C2%A3")

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
        self.assertEqual((r1.body, r2.body), (None, "New body"))
        self.assertEqual((r1.headers, r2.headers), ({}, hdrs))

    def test_httprepr(self):
        r1 = Request("http://www.example.com")
        self.assertEqual(r1.httprepr(), 'GET http://www.example.com HTTP/1.1\r\nHost: www.example.com\r\n\r\n')

        r1 = Request("http://www.example.com", method='POST', headers={"Content-type": "text/html"}, body="Some body")
        self.assertEqual(r1.httprepr(), 'POST http://www.example.com HTTP/1.1\r\nHost: www.example.com\r\nContent-Type: text/html\r\n\r\nSome body\r\n')

if __name__ == "__main__":
    unittest.main()
