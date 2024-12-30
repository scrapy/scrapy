from __future__ import annotations

import json
import unittest
import warnings
from hashlib import sha1
from weakref import WeakKeyDictionary

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.utils.python import to_bytes
from scrapy.utils.request import (
    _fingerprint_cache,
    fingerprint,
    request_authenticate,
    request_httprepr,
    request_to_curl,
)
from scrapy.utils.test import get_crawler


class UtilsRequestTest(unittest.TestCase):
    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_request_authenticate(self):
        r = Request("http://www.example.com")
        request_authenticate(r, "someuser", "somepass")
        self.assertEqual(r.headers["Authorization"], b"Basic c29tZXVzZXI6c29tZXBhc3M=")

    def test_request_httprepr(self):
        r1 = Request("http://www.example.com")
        self.assertEqual(
            request_httprepr(r1), b"GET / HTTP/1.1\r\nHost: www.example.com\r\n\r\n"
        )

        r1 = Request("http://www.example.com/some/page.html?arg=1")
        self.assertEqual(
            request_httprepr(r1),
            b"GET /some/page.html?arg=1 HTTP/1.1\r\nHost: www.example.com\r\n\r\n",
        )

        r1 = Request(
            "http://www.example.com",
            method="POST",
            headers={"Content-type": b"text/html"},
            body=b"Some body",
        )
        self.assertEqual(
            request_httprepr(r1),
            b"POST / HTTP/1.1\r\nHost: www.example.com\r\nContent-Type: text/html\r\n\r\nSome body",
        )

    def test_request_httprepr_for_non_http_request(self):
        # the representation is not important but it must not fail.
        request_httprepr(Request("file:///tmp/foo.txt"))
        request_httprepr(Request("ftp://localhost/tmp/foo.txt"))


class FingerprintTest(unittest.TestCase):
    maxDiff = None

    function: staticmethod = staticmethod(fingerprint)
    cache: (
        WeakKeyDictionary[Request, dict[tuple[tuple[bytes, ...] | None, bool], bytes]]
        | WeakKeyDictionary[Request, dict[tuple[tuple[bytes, ...] | None, bool], str]]
    ) = _fingerprint_cache
    default_cache_key = (None, False)
    known_hashes: tuple[tuple[Request, bytes | str, dict], ...] = (
        (
            Request("http://example.org"),
            b"xs\xd7\x0c3uj\x15\xfe\xd7d\x9b\xa9\t\xe0d\xbf\x9cXD",
            {},
        ),
        (
            Request("https://example.org"),
            b"\xc04\x85P,\xaa\x91\x06\xf8t\xb4\xbd*\xd9\xe9\x8a:m\xc3l",
            {},
        ),
        (
            Request("https://example.org?a"),
            b"G\xad\xb8Ck\x19\x1c\xed\x838,\x01\xc4\xde;\xee\xa5\x94a\x0c",
            {},
        ),
        (
            Request("https://example.org?a=b"),
            b"\x024MYb\x8a\xc2\x1e\xbc>\xd6\xac*\xda\x9cF\xc1r\x7f\x17",
            {},
        ),
        (
            Request("https://example.org?a=b&a"),
            b"t+\xe8*\xfb\x84\xe3v\x1a}\x88p\xc0\xccB\xd7\x9d\xfez\x96",
            {},
        ),
        (
            Request("https://example.org?a=b&a=c"),
            b"\xda\x1ec\xd0\x9c\x08s`\xb4\x9b\xe2\xb6R\xf8k\xef\xeaQG\xef",
            {},
        ),
        (
            Request("https://example.org", method="POST"),
            b"\x9d\xcdA\x0fT\x02:\xca\xa0}\x90\xda\x05B\xded\x8aN7\x1d",
            {},
        ),
        (
            Request("https://example.org", body=b"a"),
            b"\xc34z>\xd8\x99\x8b\xda7\x05r\x99I\xa8\xa0x;\xa41_",
            {},
        ),
        (
            Request("https://example.org", method="POST", body=b"a"),
            b"5`\xe2y4\xd0\x9d\xee\xe0\xbatw\x87Q\xe8O\xd78\xfc\xe7",
            {},
        ),
        (
            Request("https://example.org#a", headers={"A": b"B"}),
            b"\xc04\x85P,\xaa\x91\x06\xf8t\xb4\xbd*\xd9\xe9\x8a:m\xc3l",
            {},
        ),
        (
            Request("https://example.org#a", headers={"A": b"B"}),
            b"]\xc7\x1f\xf2\xafG2\xbc\xa4\xfa\x99\n33\xda\x18\x94\x81U.",
            {"include_headers": ["A"]},
        ),
        (
            Request("https://example.org#a", headers={"A": b"B"}),
            b"<\x1a\xeb\x85y\xdeW\xfb\xdcq\x88\xee\xaf\x17\xdd\x0c\xbfH\x18\x1f",
            {"keep_fragments": True},
        ),
        (
            Request("https://example.org#a", headers={"A": b"B"}),
            b"\xc1\xef~\x94\x9bS\xc1\x83\t\xdcz8\x9f\xdc{\x11\x16I.\x11",
            {"include_headers": ["A"], "keep_fragments": True},
        ),
        (
            Request("https://example.org/ab"),
            b"N\xe5l\xb8\x12@iw\xe2\xf3\x1bp\xea\xffp!u\xe2\x8a\xc6",
            {},
        ),
        (
            Request("https://example.org/a", body=b"b"),
            b"_NOv\xbco$6\xfcW\x9f\xb24g\x9f\xbb\xdd\xa82\xc5",
            {},
        ),
    )

    def test_query_string_key_order(self):
        r1 = Request("http://www.example.com/query?id=111&cat=222")
        r2 = Request("http://www.example.com/query?cat=222&id=111")
        self.assertEqual(self.function(r1), self.function(r1))
        self.assertEqual(self.function(r1), self.function(r2))

    def test_query_string_key_without_value(self):
        r1 = Request("http://www.example.com/hnnoticiaj1.aspx?78132,199")
        r2 = Request("http://www.example.com/hnnoticiaj1.aspx?78160,199")
        self.assertNotEqual(self.function(r1), self.function(r2))

    def test_caching(self):
        r1 = Request("http://www.example.com/hnnoticiaj1.aspx?78160,199")
        self.assertEqual(self.function(r1), self.cache[r1][self.default_cache_key])

    def test_header(self):
        r1 = Request("http://www.example.com/members/offers.html")
        r2 = Request("http://www.example.com/members/offers.html")
        r2.headers["SESSIONID"] = b"somehash"
        self.assertEqual(self.function(r1), self.function(r2))

    def test_headers(self):
        r1 = Request("http://www.example.com/")
        r2 = Request("http://www.example.com/")
        r2.headers["Accept-Language"] = b"en"
        r3 = Request("http://www.example.com/")
        r3.headers["Accept-Language"] = b"en"
        r3.headers["SESSIONID"] = b"somehash"

        self.assertEqual(self.function(r1), self.function(r2), self.function(r3))

        self.assertEqual(
            self.function(r1), self.function(r1, include_headers=["Accept-Language"])
        )

        self.assertNotEqual(
            self.function(r1), self.function(r2, include_headers=["Accept-Language"])
        )

        self.assertEqual(
            self.function(r3, include_headers=["accept-language", "sessionid"]),
            self.function(r3, include_headers=["SESSIONID", "Accept-Language"]),
        )

    def test_fragment(self):
        r1 = Request("http://www.example.com/test.html")
        r2 = Request("http://www.example.com/test.html#fragment")
        self.assertEqual(self.function(r1), self.function(r2))
        self.assertEqual(self.function(r1), self.function(r1, keep_fragments=True))
        self.assertNotEqual(self.function(r2), self.function(r2, keep_fragments=True))
        self.assertNotEqual(self.function(r1), self.function(r2, keep_fragments=True))

    def test_method_and_body(self):
        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com", method="POST")
        r3 = Request("http://www.example.com", method="POST", body=b"request body")

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
        r2 = Request("http://www.example.com/f", body=b"oo")
        fp2 = self.function(r2)
        self.assertNotEqual(fp1, fp2)

    def test_hashes(self):
        """Test hardcoded hashes, to make sure future changes to not introduce
        backward incompatibilities."""
        actual = [
            self.function(request, **kwargs) for request, _, kwargs in self.known_hashes
        ]
        expected = [_fingerprint for _, _fingerprint, _ in self.known_hashes]
        self.assertEqual(actual, expected)


REQUEST_OBJECTS_TO_TEST = (
    Request("http://www.example.com/"),
    Request("http://www.example.com/query?id=111&cat=222"),
    Request("http://www.example.com/query?cat=222&id=111"),
    Request("http://www.example.com/hnnoticiaj1.aspx?78132,199"),
    Request("http://www.example.com/hnnoticiaj1.aspx?78160,199"),
    Request("http://www.example.com/members/offers.html"),
    Request(
        "http://www.example.com/members/offers.html",
        headers={"SESSIONID": b"somehash"},
    ),
    Request(
        "http://www.example.com/",
        headers={"Accept-Language": b"en"},
    ),
    Request(
        "http://www.example.com/",
        headers={
            "Accept-Language": b"en",
            "SESSIONID": b"somehash",
        },
    ),
    Request("http://www.example.com/test.html"),
    Request("http://www.example.com/test.html#fragment"),
    Request("http://www.example.com", method="POST"),
    Request("http://www.example.com", method="POST", body=b"request body"),
)


class RequestFingerprinterTestCase(unittest.TestCase):
    def test_default_implementation(self):
        crawler = get_crawler()
        request = Request("https://example.com")
        self.assertEqual(
            crawler.request_fingerprinter.fingerprint(request),
            fingerprint(request),
        )

    def test_deprecated_implementation(self):
        settings = {
            "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        }
        with warnings.catch_warnings(record=True) as logged_warnings:
            crawler = get_crawler(settings_dict=settings)
        request = Request("https://example.com")
        self.assertEqual(
            crawler.request_fingerprinter.fingerprint(request),
            fingerprint(request),
        )
        self.assertTrue(logged_warnings)


class CustomRequestFingerprinterTestCase(unittest.TestCase):
    def test_include_headers(self):
        class RequestFingerprinter:
            def fingerprint(self, request):
                return fingerprint(request, include_headers=["X-ID"])

        settings = {
            "REQUEST_FINGERPRINTER_CLASS": RequestFingerprinter,
        }
        crawler = get_crawler(settings_dict=settings)

        r1 = Request("http://www.example.com", headers={"X-ID": "1"})
        fp1 = crawler.request_fingerprinter.fingerprint(r1)
        r2 = Request("http://www.example.com", headers={"X-ID": "2"})
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
            "REQUEST_FINGERPRINTER_CLASS": RequestFingerprinter,
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
                if "fingerprint" in request.meta:
                    return request.meta["fingerprint"]
                return fingerprint(request)

        settings = {
            "REQUEST_FINGERPRINTER_CLASS": RequestFingerprinter,
        }
        crawler = get_crawler(settings_dict=settings)

        r1 = Request("http://www.example.com")
        fp1 = crawler.request_fingerprinter.fingerprint(r1)
        r2 = Request("http://www.example.com", meta={"fingerprint": "a"})
        fp2 = crawler.request_fingerprinter.fingerprint(r2)
        r3 = Request("http://www.example.com", meta={"fingerprint": "a"})
        fp3 = crawler.request_fingerprinter.fingerprint(r3)
        r4 = Request("http://www.example.com", meta={"fingerprint": "b"})
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
                self._fingerprint = crawler.settings["FINGERPRINT"]

            def fingerprint(self, request):
                return self._fingerprint

        settings = {
            "REQUEST_FINGERPRINTER_CLASS": RequestFingerprinter,
            "FINGERPRINT": b"fingerprint",
        }
        crawler = get_crawler(settings_dict=settings)

        request = Request("http://www.example.com")
        fingerprint = crawler.request_fingerprinter.fingerprint(request)
        self.assertEqual(fingerprint, settings["FINGERPRINT"])

    def test_from_settings(self):
        class RequestFingerprinter:
            @classmethod
            def from_settings(cls, settings):
                return cls(settings)

            def __init__(self, settings):
                self._fingerprint = settings["FINGERPRINT"]

            def fingerprint(self, request):
                return self._fingerprint

        settings = {
            "REQUEST_FINGERPRINTER_CLASS": RequestFingerprinter,
            "FINGERPRINT": b"fingerprint",
        }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            crawler = get_crawler(settings_dict=settings)

        request = Request("http://www.example.com")
        fingerprint = crawler.request_fingerprinter.fingerprint(request)
        self.assertEqual(fingerprint, settings["FINGERPRINT"])

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
                self._fingerprint = crawler.settings["FINGERPRINT"]

            def fingerprint(self, request):
                return self._fingerprint

        settings = {
            "REQUEST_FINGERPRINTER_CLASS": RequestFingerprinter,
            "FINGERPRINT": b"fingerprint",
        }
        crawler = get_crawler(settings_dict=settings)

        request = Request("http://www.example.com")
        fingerprint = crawler.request_fingerprinter.fingerprint(request)
        self.assertEqual(fingerprint, settings["FINGERPRINT"])


class RequestToCurlTest(unittest.TestCase):
    def _test_request(self, request_object, expected_curl_command):
        curl_command = request_to_curl(request_object)
        self.assertEqual(curl_command, expected_curl_command)

    def test_get(self):
        request_object = Request("https://www.example.com")
        expected_curl_command = "curl -X GET https://www.example.com"
        self._test_request(request_object, expected_curl_command)

    def test_post(self):
        request_object = Request(
            "https://www.httpbin.org/post",
            method="POST",
            body=json.dumps({"foo": "bar"}),
        )
        expected_curl_command = (
            'curl -X POST https://www.httpbin.org/post --data-raw \'{"foo": "bar"}\''
        )
        self._test_request(request_object, expected_curl_command)

    def test_headers(self):
        request_object = Request(
            "https://www.httpbin.org/post",
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body=json.dumps({"foo": "bar"}),
        )
        expected_curl_command = (
            "curl -X POST https://www.httpbin.org/post"
            ' --data-raw \'{"foo": "bar"}\''
            " -H 'Content-Type: application/json' -H 'Accept: application/json'"
        )
        self._test_request(request_object, expected_curl_command)

    def test_cookies_dict(self):
        request_object = Request(
            "https://www.httpbin.org/post",
            method="POST",
            cookies={"foo": "bar"},
            body=json.dumps({"foo": "bar"}),
        )
        expected_curl_command = (
            "curl -X POST https://www.httpbin.org/post"
            " --data-raw '{\"foo\": \"bar\"}' --cookie 'foo=bar'"
        )
        self._test_request(request_object, expected_curl_command)

    def test_cookies_list(self):
        request_object = Request(
            "https://www.httpbin.org/post",
            method="POST",
            cookies=[{"foo": "bar"}],
            body=json.dumps({"foo": "bar"}),
        )
        expected_curl_command = (
            "curl -X POST https://www.httpbin.org/post"
            " --data-raw '{\"foo\": \"bar\"}' --cookie 'foo=bar'"
        )
        self._test_request(request_object, expected_curl_command)


if __name__ == "__main__":
    unittest.main()
