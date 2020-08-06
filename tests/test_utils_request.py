import unittest

import pytest

from scrapy.http import Request
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.request import (
    _deprecated_fingerprint_cache,
    _fingerprint_cache,
    fingerprint,
    request_authenticate,
    request_fingerprint,
    request_httprepr,
)


class UtilsRequestTest(unittest.TestCase):

    def test_request_authenticate(self):
        r = Request("http://www.example.com")
        request_authenticate(r, 'someuser', 'somepass')
        self.assertEqual(r.headers['Authorization'], b'Basic c29tZXVzZXI6c29tZXBhc3M=')

    def test_request_httprepr(self):
        r1 = Request("http://www.example.com")
        self.assertEqual(request_httprepr(r1), b'GET / HTTP/1.1\r\nHost: www.example.com\r\n\r\n')

        r1 = Request("http://www.example.com/some/page.html?arg=1")
        self.assertEqual(request_httprepr(r1), b'GET /some/page.html?arg=1 HTTP/1.1\r\nHost: www.example.com\r\n\r\n')

        r1 = Request("http://www.example.com", method='POST',
                     headers={"Content-type": b"text/html"}, body=b"Some body")
        self.assertEqual(
            request_httprepr(r1),
            b'POST / HTTP/1.1\r\nHost: www.example.com\r\nContent-Type: text/html\r\n\r\nSome body'
        )

    def test_request_httprepr_for_non_http_request(self):
        # the representation is not important but it must not fail.
        request_httprepr(Request("file:///tmp/foo.txt"))
        request_httprepr(Request("ftp://localhost/tmp/foo.txt"))


class FingerprintTest(unittest.TestCase):
    function = staticmethod(fingerprint)
    cache = _fingerprint_cache

    def test_function(self):
        r1 = Request("http://www.example.com/query?id=111&cat=222")
        r2 = Request("http://www.example.com/query?cat=222&id=111")
        self.assertEqual(self.function(r1), self.function(r1))
        self.assertEqual(self.function(r1), self.function(r2))

        r1 = Request('http://www.example.com/hnnoticiaj1.aspx?78132,199')
        r2 = Request('http://www.example.com/hnnoticiaj1.aspx?78160,199')
        self.assertNotEqual(self.function(r1), self.function(r2))

        # make sure caching is working
        self.assertEqual(self.function(r1), self.cache[r1][(None, False)])

        r1 = Request("http://www.example.com/members/offers.html")
        r2 = Request("http://www.example.com/members/offers.html")
        r2.headers['SESSIONID'] = b"somehash"
        self.assertEqual(self.function(r1), self.function(r2))

        r1 = Request("http://www.example.com/")
        r2 = Request("http://www.example.com/")
        r2.headers['Accept-Language'] = b'en'
        r3 = Request("http://www.example.com/")
        r3.headers['Accept-Language'] = b'en'
        r3.headers['SESSIONID'] = b"somehash"

        self.assertEqual(self.function(r1), self.function(r2), self.function(r3))

        self.assertEqual(self.function(r1),
                         self.function(r1, include_headers=['Accept-Language']))

        self.assertNotEqual(
            self.function(r1),
            self.function(r2, include_headers=['Accept-Language']))

        self.assertEqual(self.function(r3, include_headers=['accept-language', 'sessionid']),
                         self.function(r3, include_headers=['SESSIONID', 'Accept-Language']))

        r1 = Request("http://www.example.com/test.html")
        r2 = Request("http://www.example.com/test.html#fragment")
        self.assertEqual(self.function(r1), self.function(r2))
        self.assertEqual(self.function(r1), self.function(r1, keep_fragments=True))
        self.assertNotEqual(self.function(r2), self.function(r2, keep_fragments=True))
        self.assertNotEqual(self.function(r1), self.function(r2, keep_fragments=True))

        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com", method='POST')
        r3 = Request("http://www.example.com", method='POST', body=b'request body')

        self.assertNotEqual(self.function(r1), self.function(r2))
        self.assertNotEqual(self.function(r2), self.function(r3))

        # cached fingerprint must be cleared on request copy
        r1 = Request("http://www.example.com")
        fp1 = self.function(r1)
        r2 = r1.replace(url="http://www.example.com/other")
        fp2 = self.function(r2)
        self.assertNotEqual(fp1, fp2)


class RequestFingerprintTest(FingerprintTest):
    function = staticmethod(request_fingerprint)
    cache = _deprecated_fingerprint_cache

    def test_deprecation(self):
        with pytest.warns(ScrapyDeprecationWarning) as warnings:
            self.function(Request("http://www.example.com"))
        actual = [str(warning.message) for warning in warnings]
        expected = ['Call to deprecated function request_fingerprint. Use '
                    'scrapy.utils.request.fingerprint instead.']
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
