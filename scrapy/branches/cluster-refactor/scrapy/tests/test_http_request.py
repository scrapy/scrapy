import unittest
from scrapy.http import Request, Headers
from scrapy.core.scheduler import GroupFilter

class RequestTest(unittest.TestCase):
    """ c14n comparison functions """

    def test_groupfilter(self):
        k1 = Request(url="http://www.scrapy.org/path?key=val").fingerprint()
        k2 = Request(url="http://www.scrapy.org/path?key=val&key=val").fingerprint()
        self.assertEqual(k1, k2)

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
        for k,v in h.iteritems():
            self.assert_(isinstance(k, str))
            self.assert_(isinstance(v, str))

        r = Request(url="http://www.example.org/1", referer=u"http://www.example.org")
        self.assert_(isinstance(r.headers['referer'], str))

    def test_eq(self):
        url = 'http://www.scrapy.org'
        r1 = Request(url=url)
        r2 = Request(url=url)
        self.assertNotEqual(r1, r2)

        set_ = set()
        set_.add(r1)
        set_.add(r2)
        self.assertEqual(len(set_), 2)

    def test_fingerprint(self):
        url = 'http://www.scrapy.org'
        r = Request(url=url)
        urlhash = r.fingerprint()

        # fingerprint including all initials headers
        r.fingerprint_params['exclude_headers'] = []
        fullhash = r.fingerprint()
        del r.fingerprint_params['exclude_headers']

        # all headers are excluded from fingerprint by default
        r.headers['Accept'] = 'application/json'
        accepthash = r.fingerprint()
        r.headers['User-Agent'] = 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.8.1.8) Gecko/20071004 Iceweasel/2.0.0.8 (Debian-2.0.0.8-1)'
        useragenthash = r.fingerprint()
        self.assertEqual(urlhash, accepthash)
        self.assertEqual(urlhash, useragenthash)
        self.assertEqual(accepthash, useragenthash)

        # take User-Agent header in count as specified in `include_headers`
        r.fingerprint_params['include_headers'] = ['user-agent']
        useragenthash = r.fingerprint()
        self.assertNotEqual(useragenthash, urlhash)

        # include_headers has precedence over exclude_headers
        r.fingerprint_params['exclude_headers'] = ['user-agent', 'Accept']
        self.assertEqual(useragenthash, r.fingerprint())

        del r.fingerprint_params['include_headers']
        self.assertNotEqual(useragenthash, r.fingerprint()) # exclude_headers is excluding 'User-Agent' from hash
        self.assertEqual(fullhash, r.fingerprint()) # all headers previously seted was excluded

        # set more headers
        r.headers['Accept-Language'] = 'en-us,en;q=0.5'
        r.headers['SESSIONID'] = 'an ugly session id header'
        self.assertNotEqual(urlhash, r.fingerprint())

        # force emtpy include_headers (ignore exclude_headers)
        r.fingerprint_params['include_headers'] = []
        self.assertEqual(urlhash, r.fingerprint())

        # Tamper Function
        r.fingerprint_params['tamperfunc'] = lambda req: Request(url=req.url)
        self.assertEqual(urlhash, r.fingerprint())

        # Compare request with None vs {} header
        r = Request(url=url, headers=None)
        o = Request(url=url, headers={})
        self.assertEqual(o.fingerprint(), r.fingerprint())
        self.assertNotEqual(r, o)

        # Different ways of setting headers attribute
        headers = {'Accept':'gzip', 'Custom-Header':'nothing to tell you'}
        r = Request(url=url, headers=headers)
        p = Request(url=url, headers=r.headers)
        o = Request(url=url)
        o.headers = headers
        self.assertEqual(r.fingerprint(), o.fingerprint())
        self.assertEqual(r.fingerprint(), p.fingerprint())
        self.assertEqual(o.fingerprint(), p.fingerprint())
        self.assertNotEqual(r, o)
        self.assertNotEqual(r, p)
        self.assertNotEqual(o, p)

        # same url, implicit method
        r1 = Request(url=url)
        r2 = Request(url=url, method='GET')
        self.assertEqual(r1.fingerprint(), r2.fingerprint())

        # same url, different method
        r3 = Request(url=url, method='POST')
        self.assertNotEqual(r1.fingerprint(), r3.fingerprint())

        # implicit POST method
        r3.body = ''
        r4 = Request(url=url, body='')
        self.assertEqual(r3.fingerprint(), r4.fingerprint())

        # body is not important in GET or DELETE
        r1 = Request(url=url, method='get', body='data')
        r2 = Request(url=url, method='get')
        self.assertEqual(r1.fingerprint(), r2.fingerprint())

        r1 = Request(url=url, method='delete', body='data')
        r2 = Request(url=url, method='delete')
        self.assertEqual(r1.fingerprint(), r2.fingerprint())

        # no body by default
        r1 = Request(url=url, method='POST')
        r2 = Request(url=url, method='POST', body=None)
        self.assertEqual(r1.fingerprint(), r2.fingerprint())

        # empty body is equal to None body
        r3 = Request(url=url, method='POST', body='')
        self.assertEqual(r1.fingerprint(), r3.fingerprint())

    def test_insensitive_request_fingerprints(self):
        url = 'http://www.scrapy.org'
        fp = {'include_headers':['Accept','Content-Type']}
        r1a = Request(url=url.lower())
        r1b = Request(url=url.upper())
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())

        r1a = Request(url=url.lower(), method='get')
        r1b = Request(url=url.upper(), method='GET')
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())

        r1c = Request(url=url.upper(), method='GET', body='this is not important')
        self.assertEqual(r1b.fingerprint(), r1c.fingerprint())

        r1a = Request(url=url.lower(), method='get', fingerprint_params=fp)
        r1b = Request(url=url.upper(), method='GET', fingerprint_params=fp)
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())

        r1a = Request(url=url.lower(), method='get', headers={'ACCEPT':'Black'})
        r1b = Request(url=url.upper(), method='GET', headers={'ACCEPT':'Black'})
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())

        r1a = Request(url=url.lower(), method='get', fingerprint_params=fp, headers={'ACCEPT':'Black'})
        r1b = Request(url=url.upper(), method='GET', fingerprint_params=fp, headers={'ACCEPT':'Black'})
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())

        r1a = Request(url=url.lower(), method='get', fingerprint_params=fp, headers={'ACCEPT':'Black'})
        r1b = Request(url=url.upper(), method='GET', fingerprint_params=fp, headers={'Accept':'Black'})
        r1c = Request(url=url.upper(), method='gEt', fingerprint_params=fp, headers={'accept':'Black'})
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())
        self.assertEqual(r1a.fingerprint(), r1c.fingerprint())

        r1a = Request(url=url.lower(), method='get', fingerprint_params=fp, headers={'ACCEPT':'Black', 'content-type':'application/json'})
        r1b = Request(url=url.upper(), method='GET', fingerprint_params=fp, headers={'Accept':'Black', 'Content-Type':'application/json'})
        r1c = Request(url=url.upper(), method='Get', fingerprint_params=fp, headers={'accepT':'Black', 'CONTENT-TYPE':'application/json'})
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())
        self.assertEqual(r1a.fingerprint(), r1c.fingerprint())

        r1a = Request(url=url.lower(), method='Post', fingerprint_params=fp, headers={'ACCEPT':'Black', 'content-type':'application/json'})
        r1b = Request(url=url.upper(), method='POST', fingerprint_params=fp, headers={'Accept':'Black', 'Content-Type':'application/json'})
        r1c = Request(url=url.upper(), method='posT', fingerprint_params=fp, headers={'accepT':'Black', 'CONTENT-TYPE':'application/json'})
        self.assertEqual(r1a.fingerprint(), r1b.fingerprint())
        self.assertEqual(r1a.fingerprint(), r1c.fingerprint())

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

if __name__ == "__main__":
    unittest.main()


