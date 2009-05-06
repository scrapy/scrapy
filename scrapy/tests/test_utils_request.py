import unittest
from scrapy.http import Request
from scrapy.utils.request import request_fingerprint, request_authenticate

class UtilsRequestTest(unittest.TestCase):

    def test_request_fingerprint(self):
        url = 'http://www.scrapy.org'
        r = Request(url=url)
        urlhash = request_fingerprint(r)

        r1 = Request("http://www.example.com/query?id=111&cat=222")
        r2 = Request("http://www.example.com/query?cat=222&id=111")
        self.assertEqual(request_fingerprint(r1), request_fingerprint(r1))
        self.assertEqual(request_fingerprint(r1), request_fingerprint(r2))

        r1 = Request('http://www.example.com/hnnoticiaj1.aspx?78132,199')
        r2 = Request('http://www.example.com/hnnoticiaj1.aspx?78160,199')
        self.assertNotEqual(request_fingerprint(r1), request_fingerprint(r2))

        # make sure caching is working
        self.assertEqual(request_fingerprint(r1), r1.cache['fingerprint'])

        r1 = Request("http://www.example.com/members/offers.html")
        r2 = Request("http://www.example.com/members/offers.html")
        r2.headers['SESSIONID'] = "somehash"
        self.assertEqual(request_fingerprint(r1), request_fingerprint(r2))

        r1 = Request("http://www.example.com/")
        r2 = Request("http://www.example.com/")
        r2.headers['Accept-Language'] = 'en'
        r3 = Request("http://www.example.com/")
        r3.headers['Accept-Language'] = 'en'
        r3.headers['SESSIONID'] = "somehash"

        self.assertEqual(request_fingerprint(r1), request_fingerprint(r2), request_fingerprint(r3))

        self.assertEqual(request_fingerprint(r1),
                         request_fingerprint(r1, include_headers=['Accept-Language']))

        self.assertNotEqual(request_fingerprint(r1),
                         request_fingerprint(r2, include_headers=['Accept-Language']))

        self.assertEqual(request_fingerprint(r3, include_headers=['accept-language', 'sessionid']),
                         request_fingerprint(r3, include_headers=['SESSIONID', 'Accept-Language']))

        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com", method='POST')
        r3 = Request("http://www.example.com", method='POST', body='request body')

        self.assertNotEqual(request_fingerprint(r1), request_fingerprint(r2))
        self.assertNotEqual(request_fingerprint(r2), request_fingerprint(r3))

        # cached fingerprint must be cleared on request copy
        r1 = Request("http://www.example.com")
        fp1 = request_fingerprint(r1)
        r2 = r1.copy()
        r2.url = "http://www.example.com/other"
        fp2 = request_fingerprint(r2)
        self.assertNotEqual(fp1, fp2)


    def test_request_authenticate(self):
        r = Request("http://www.example.com")
        request_authenticate(r, 'someuser', 'somepass')
        self.assertEqual(r.headers['Authorization'], 'Basic c29tZXVzZXI6c29tZXBhc3M=')

if __name__ == "__main__":
    unittest.main()
