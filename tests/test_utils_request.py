import unittest
import warnings
from hashlib import sha1
from typing import Mapping, Tuple
from weakref import WeakKeyDictionary

import pytest
from w3lib.url import canonicalize_url

from scrapy.http import Request
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.python import to_bytes
from scrapy.utils.request import (
    _deprecated_fingerprint_cache,
    _fingerprint_cache,
    _request_fingerprint_as_bytes,
    fingerprint,
    request_authenticate,
    request_fingerprint,
    request_httprepr,
)
from scrapy.utils.test import get_crawler


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
    default_cache_key = (None, False)

    def test_query_string_key_order(self):
        r1 = Request("http://www.example.com/query?id=111&cat=222")
        r2 = Request("http://www.example.com/query?cat=222&id=111")
        self.assertEqual(self.function(r1), self.function(r1))
        self.assertEqual(self.function(r1), self.function(r2))

    def test_query_string_key_without_value(self):
        r1 = Request('http://www.example.com/hnnoticiaj1.aspx?78132,199')
        r2 = Request('http://www.example.com/hnnoticiaj1.aspx?78160,199')
        self.assertNotEqual(self.function(r1), self.function(r2))

    def test_caching(self):
        r1 = Request('http://www.example.com/hnnoticiaj1.aspx?78160,199')
        self.assertEqual(
            self.function(r1),
            self.cache[r1][self.default_cache_key]
        )

    def test_header(self):
        r1 = Request("http://www.example.com/members/offers.html")
        r2 = Request("http://www.example.com/members/offers.html")
        r2.headers['SESSIONID'] = b"somehash"
        self.assertEqual(self.function(r1), self.function(r2))

    def test_headers(self):
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

    def test_fragment(self):
        r1 = Request("http://www.example.com/test.html")
        r2 = Request("http://www.example.com/test.html#fragment")
        self.assertEqual(self.function(r1), self.function(r2))
        self.assertEqual(self.function(r1), self.function(r1, keep_fragments=True))
        self.assertNotEqual(self.function(r2), self.function(r2, keep_fragments=True))
        self.assertNotEqual(self.function(r1), self.function(r2, keep_fragments=True))

    def test_method_and_body(self):
        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com", method='POST')
        r3 = Request("http://www.example.com", method='POST', body=b'request body')

        self.assertNotEqual(self.function(r1), self.function(r2))
        self.assertNotEqual(self.function(r2), self.function(r3))

    def test_request_replace(self):
        # cached fingerprint must be cleared on request copy
        r1 = Request("http://www.example.com")
        fp1 = self.function(r1)
        r2 = r1.replace(url="http://www.example.com/other")
        fp2 = self.function(r2)
        self.assertNotEqual(fp1, fp2)

    def test_part_separation(self):
        # An old implementation used to serialize request data in a way that
        # would put the body right after the URL.
        r1 = Request("http://www.example.com/foo")
        fp1 = self.function(r1)
        r2 = Request("http://www.example.com/f", body=b'oo')
        fp2 = self.function(r2)
        self.assertNotEqual(fp1, fp2)


class RequestFingerprintTest(FingerprintTest):
    function = staticmethod(request_fingerprint)
    cache = _deprecated_fingerprint_cache

    @pytest.mark.xfail(reason='known bug kept for backward compatibility', strict=True)
    def test_part_separation(self):
        super().test_part_separation()

    def test_deprecation_default_parameters(self):
        with pytest.warns(ScrapyDeprecationWarning) as warnings:
            self.function(Request("http://www.example.com"))
        messages = [str(warning.message) for warning in warnings]
        self.assertTrue(
            any(
                'Call to deprecated function' in message
                for message in messages
            )
        )
        self.assertFalse(any('non-default' in message for message in messages))

    def test_deprecation_non_default_parameters(self):
        with pytest.warns(ScrapyDeprecationWarning) as warnings:
            self.function(Request("http://www.example.com"), keep_fragments=True)
        messages = [str(warning.message) for warning in warnings]
        self.assertTrue(
            any(
                'Call to deprecated function' in message
                for message in messages
            )
        )
        self.assertTrue(any('non-default' in message for message in messages))


class RequestFingerprintAsBytesTest(FingerprintTest):
    function = staticmethod(_request_fingerprint_as_bytes)
    cache = _deprecated_fingerprint_cache

    def test_caching(self):
        r1 = Request('http://www.example.com/hnnoticiaj1.aspx?78160,199')
        self.assertEqual(
            self.function(r1),
            bytes.fromhex(self.cache[r1][self.default_cache_key])
        )

    @pytest.mark.xfail(reason='known bug kept for backward compatibility', strict=True)
    def test_part_separation(self):
        super().test_part_separation()


_fingerprint_cache_2_3: Mapping[Request, Tuple[None, bool]] = WeakKeyDictionary()


def request_fingerprint_2_3(request, include_headers=None, keep_fragments=False):
    if include_headers:
        include_headers = tuple(to_bytes(h.lower()) for h in sorted(include_headers))
    cache = _fingerprint_cache_2_3.setdefault(request, {})
    cache_key = (include_headers, keep_fragments)
    if cache_key not in cache:
        fp = sha1()
        fp.update(to_bytes(request.method))
        fp.update(to_bytes(canonicalize_url(request.url, keep_fragments=keep_fragments)))
        fp.update(request.body or b'')
        if include_headers:
            for hdr in include_headers:
                if hdr in request.headers:
                    fp.update(hdr)
                    for v in request.headers.getlist(hdr):
                        fp.update(v)
        cache[cache_key] = fp.hexdigest()
    return cache[cache_key]


@pytest.mark.parametrize(
    'request_object',
    (
        Request("http://www.example.com/"),
        Request("http://www.example.com/query?id=111&cat=222"),
        Request("http://www.example.com/query?cat=222&id=111"),
        Request('http://www.example.com/hnnoticiaj1.aspx?78132,199'),
        Request('http://www.example.com/hnnoticiaj1.aspx?78160,199'),
        Request("http://www.example.com/members/offers.html"),
        Request(
            "http://www.example.com/members/offers.html",
            headers={'SESSIONID': b"somehash"},
        ),
        Request(
            "http://www.example.com/",
            headers={'Accept-Language': b"en"},
        ),
        Request(
            "http://www.example.com/",
            headers={
                'Accept-Language': b"en",
                'SESSIONID': b"somehash",
            },
        ),
        Request("http://www.example.com/test.html"),
        Request("http://www.example.com/test.html#fragment"),
        Request("http://www.example.com", method='POST'),
        Request("http://www.example.com", method='POST', body=b'request body'),
    )
)
@pytest.mark.parametrize(
    'include_headers',
    (
        None,
        ['Accept-Language'],
        ['accept-language', 'sessionid'],
        ['SESSIONID', 'Accept-Language'],
    ),
)
@pytest.mark.parametrize(
    'keep_fragments',
    (
        False,
        True,
    ),
)
def test_function_backward_compatibility(request_object, include_headers, keep_fragments):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fp = request_fingerprint(
            request_object,
            include_headers=include_headers,
            keep_fragments=keep_fragments,
        )
    old_fp = request_fingerprint_2_3(
        request_object,
        include_headers=include_headers,
        keep_fragments=keep_fragments,
    )
    assert fp == old_fp


@pytest.mark.parametrize(
    'request_object',
    (
        Request("http://www.example.com/"),
        Request("http://www.example.com/query?id=111&cat=222"),
        Request("http://www.example.com/query?cat=222&id=111"),
        Request('http://www.example.com/hnnoticiaj1.aspx?78132,199'),
        Request('http://www.example.com/hnnoticiaj1.aspx?78160,199'),
        Request("http://www.example.com/members/offers.html"),
        Request(
            "http://www.example.com/members/offers.html",
            headers={'SESSIONID': b"somehash"},
        ),
        Request(
            "http://www.example.com/",
            headers={'Accept-Language': b"en"},
        ),
        Request(
            "http://www.example.com/",
            headers={
                'Accept-Language': b"en",
                'SESSIONID': b"somehash",
            },
        ),
        Request("http://www.example.com/test.html"),
        Request("http://www.example.com/test.html#fragment"),
        Request("http://www.example.com", method='POST'),
        Request("http://www.example.com", method='POST', body=b'request body'),
    )
)
def test_component_backward_compatibility(request_object):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fp = get_crawler().request_fingerprinter.fingerprint(request_object)
    old_fp = request_fingerprint_2_3(request_object)
    assert fp.hex() == old_fp


class CustomRequestFingerprinterTestCase(unittest.TestCase):

    def test_include_headers(self):

        class RequestFingerprinter:

            def fingerprint(self, request):
                return fingerprint(request, include_headers=['X-ID'])

        settings = {
            'REQUEST_FINGERPRINTER_CLASS': RequestFingerprinter,
        }
        crawler = get_crawler(settings_dict=settings)

        r1 = Request("http://www.example.com", headers={'X-ID': '1'})
        fp1 = crawler.request_fingerprinter.fingerprint(r1)
        r2 = Request("http://www.example.com", headers={'X-ID': '2'})
        fp2 = crawler.request_fingerprinter.fingerprint(r2)
        self.assertNotEqual(fp1, fp2)

    def test_dont_canonicalize(self):

        class RequestFingerprinter:
            cache = WeakKeyDictionary()

            def fingerprint(self, request):
                if request not in self.cache:
                    fp = sha1()
                    fp.update(to_bytes(request.url))
                    self.cache[request] = fp.digest()
                return self.cache[request]

        settings = {
            'REQUEST_FINGERPRINTER_CLASS': RequestFingerprinter,
        }
        crawler = get_crawler(settings_dict=settings)

        r1 = Request("http://www.example.com?a=1&a=2")
        fp1 = crawler.request_fingerprinter.fingerprint(r1)
        r2 = Request("http://www.example.com?a=2&a=1")
        fp2 = crawler.request_fingerprinter.fingerprint(r2)
        self.assertNotEqual(fp1, fp2)

    def test_meta(self):

        class RequestFingerprinter:

            def fingerprint(self, request):
                if 'fingerprint' in request.meta:
                    return request.meta['fingerprint']
                return fingerprint(request)

        settings = {
            'REQUEST_FINGERPRINTER_CLASS': RequestFingerprinter,
        }
        crawler = get_crawler(settings_dict=settings)

        r1 = Request("http://www.example.com")
        fp1 = crawler.request_fingerprinter.fingerprint(r1)
        r2 = Request("http://www.example.com", meta={'fingerprint': 'a'})
        fp2 = crawler.request_fingerprinter.fingerprint(r2)
        r3 = Request("http://www.example.com", meta={'fingerprint': 'a'})
        fp3 = crawler.request_fingerprinter.fingerprint(r3)
        r4 = Request("http://www.example.com", meta={'fingerprint': 'b'})
        fp4 = crawler.request_fingerprinter.fingerprint(r4)
        self.assertNotEqual(fp1, fp2)
        self.assertNotEqual(fp1, fp4)
        self.assertNotEqual(fp2, fp4)
        self.assertEqual(fp2, fp3)

    def test_from_crawler(self):

        class RequestFingerprinter:

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler)

            def __init__(self, crawler):
                self._fingerprint = crawler.settings['FINGERPRINT']

            def fingerprint(self, request):
                return self._fingerprint

        settings = {
            'REQUEST_FINGERPRINTER_CLASS': RequestFingerprinter,
            'FINGERPRINT': b'fingerprint',
        }
        crawler = get_crawler(settings_dict=settings)

        request = Request("http://www.example.com")
        fingerprint = crawler.request_fingerprinter.fingerprint(request)
        self.assertEqual(fingerprint, settings['FINGERPRINT'])

    def test_from_settings(self):

        class RequestFingerprinter:

            @classmethod
            def from_settings(cls, settings):
                return cls(settings)

            def __init__(self, settings):
                self._fingerprint = settings['FINGERPRINT']

            def fingerprint(self, request):
                return self._fingerprint

        settings = {
            'REQUEST_FINGERPRINTER_CLASS': RequestFingerprinter,
            'FINGERPRINT': b'fingerprint',
        }
        crawler = get_crawler(settings_dict=settings)

        request = Request("http://www.example.com")
        fingerprint = crawler.request_fingerprinter.fingerprint(request)
        self.assertEqual(fingerprint, settings['FINGERPRINT'])

    def test_from_crawler_and_settings(self):

        class RequestFingerprinter:

            # This method is ignored due to the presence of from_crawler
            @classmethod
            def from_settings(cls, settings):
                return cls(settings)

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler)

            def __init__(self, crawler):
                self._fingerprint = crawler.settings['FINGERPRINT']

            def fingerprint(self, request):
                return self._fingerprint

        settings = {
            'REQUEST_FINGERPRINTER_CLASS': RequestFingerprinter,
            'FINGERPRINT': b'fingerprint',
        }
        crawler = get_crawler(settings_dict=settings)

        request = Request("http://www.example.com")
        fingerprint = crawler.request_fingerprinter.fingerprint(request)
        self.assertEqual(fingerprint, settings['FINGERPRINT'])


if __name__ == "__main__":
    unittest.main()
