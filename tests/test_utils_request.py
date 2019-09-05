from __future__ import print_function

import unittest

from scrapy.http import Request
from scrapy.settings import Settings
from scrapy.utils.request import (
    json_serializer,
    process_request_fingerprint,
    request_fingerprint,
    request_authenticate,
    request_httprepr,
    sha1_hasher,
)


class JSONSerializerTests(unittest.TestCase):

    def test_json_serializer(self):
        serialized = b'{"a": 1, "b": 2}'
        assert json_serializer({'a': 1, 'b': 2}) == serialized
        assert json_serializer({'b': 2, 'a': 1}) == serialized


class ProcessRequestFingerprintTests(unittest.TestCase):

    def test_override_default_processor(self):
        request = Request('https://example.com')
        data = process_request_fingerprint(
            request, {}, url_processor=str.upper)
        assert data['url'] == 'HTTPS://EXAMPLE.COM'

    def test_capture_request_header(self):
        request = Request(
            'https://example.com', headers={'Content-Type': 'json'})
        data = process_request_fingerprint(
            request, {}, headers={'content-type'})
        assert data['headers']['content-type'] == ['json']

    def test_capture_missing_request_header(self):
        request = Request('https://example.com')
        data = process_request_fingerprint(
            request, {}, headers={'content-type'})
        assert 'headers' not in data

    def test_capture_request_metadata(self):
        meta = {'page': 1}
        request = Request('https://example.com', meta=meta)
        data = process_request_fingerprint(request, {}, meta={'page'})
        assert data['meta'] == meta
        assert id(data['meta']) != id(meta)

    def test_capture_missing_request_metadata(self):
        request = Request('https://example.com')
        data = process_request_fingerprint(request, {}, meta={'page'})
        assert 'meta' not in data


class RequestFingerprintTests(unittest.TestCase):

    def test_different_query_string_order(self):
        r1 = Request("http://www.example.com/query?id=111&cat=222")
        r2 = Request("http://www.example.com/query?cat=222&id=111")
        self.assertEqual(request_fingerprint(r1), request_fingerprint(r2))

    def test_query_string_parameter_without_value(self):
        r1 = Request('http://www.example.com/hnnoticiaj1.aspx?78132,199')
        r2 = Request('http://www.example.com/hnnoticiaj1.aspx?78160,199')
        self.assertNotEqual(request_fingerprint(r1), request_fingerprint(r2))

    def test_headers_are_ignored_by_default(self):
        r1 = Request("http://www.example.com/members/offers.html")
        r2 = Request("http://www.example.com/members/offers.html")
        r2.headers['SESSIONID'] = b"somehash"
        self.assertEqual(request_fingerprint(r1), request_fingerprint(r2))

    def test_include_headers(self):
        r1 = Request("http://www.example.com/")
        r2 = Request("http://www.example.com/")
        r2.headers['Accept-Language'] = b'en'
        r3 = Request("http://www.example.com/")
        r3.headers['Accept-Language'] = b'en'
        r3.headers['SESSIONID'] = b"somehash"
        self.assertEqual(request_fingerprint(r1), request_fingerprint(r2), request_fingerprint(r3))
        self.assertEqual(request_fingerprint(r1),
                         request_fingerprint(r1, include_headers=['Accept-Language']))
        self.assertNotEqual(request_fingerprint(r1),
                            request_fingerprint(r2, include_headers=['Accept-Language']))
        self.assertEqual(request_fingerprint(r3, include_headers=['accept-language', 'sessionid']),
                         request_fingerprint(r3, include_headers=['SESSIONID', 'Accept-Language']))

    def test_include_headers_and_request_fingerprint(self):
        fingerprint = b'1'
        request1 = Request("http://www.example.com/",
                           headers={'Accept-Language': 'en'},
                           fingerprint=fingerprint)
        request2 = Request("http://www.example.com/",
                           headers={'Accept-Language': 'en'})
        fingerprint1 = request_fingerprint(
            request1, include_headers=['Accept-Language'])
        fingerprint2 = request_fingerprint(
            request2, include_headers=['Accept-Language'])
        assert fingerprint1 == fingerprint2
        assert request1.fingerprint != fingerprint1
        assert request1.fingerprint == fingerprint

    def test_include_headers_ignores_overriders(self):
        request1 = Request("http://www.example.com/")
        fingerprint1 = request_fingerprint(request1, include_headers=['a'])
        meta = {
            'fingerprint_processors': [lambda x, y: x.url],
            'fingerprint_serializer': lambda x: x,
            'fingerprint_hasher': lambda x: x,
        }
        settings = Settings()
        settings['REQUEST_FINGERPRINT_PROCESSORS'] = [lambda x, y: x.url]
        settings['REQUEST_FINGERPRINT_SERIALIZER'] = lambda x: x
        settings['REQUEST_FINGERPRINT_HASHER'] = lambda x: x
        request2 = Request("http://www.example.com/", meta=meta)
        fingerprint2 = request_fingerprint(
            request2, include_headers=['a'], settings=settings)
        assert request1.fingerprint is None
        assert request2.fingerprint is None
        assert fingerprint1 == fingerprint2

    def test_method_and_body(self):
        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com", method='POST')
        r3 = Request("http://www.example.com", method='POST', body=b'request body')
        self.assertNotEqual(request_fingerprint(r1), request_fingerprint(r2))
        self.assertNotEqual(request_fingerprint(r2), request_fingerprint(r3))

    def test_return_predefined_fingerprint(self):
        fingerprint = b'1'
        fingerprint_string = fingerprint.hex()
        request = Request("http://www.example.com", fingerprint=fingerprint)
        output = request_fingerprint(request, settings=Settings())
        assert output == fingerprint_string
        assert request.fingerprint == fingerprint
        output = request_fingerprint(
            request, settings=Settings(), hexadecimal=False)
        assert output == fingerprint
        assert request.fingerprint == fingerprint

    def test_fingerprint_is_updated(self):
        request = Request("http://www.example.com")
        assert request.fingerprint is None
        output = request_fingerprint(
            request, settings=Settings(), hexadecimal=False)
        assert request.fingerprint == output

    def test_no_settings_and_request_fingerprint(self):
        fingerprint = b'1'
        request1 = Request("http://www.example.com/", fingerprint=fingerprint)
        request2 = Request("http://www.example.com/")
        fingerprint1 = request_fingerprint(request1)
        fingerprint2 = request_fingerprint(request2)
        assert fingerprint1 == fingerprint2
        assert request1.fingerprint != fingerprint1
        assert request1.fingerprint == fingerprint

    def test_no_settings_ignores_overriders(self):
        request1 = Request("http://www.example.com/")
        fingerprint1 = request_fingerprint(request1)
        meta = {
            'fingerprint_processors': [lambda x, y: x.url],
            'fingerprint_serializer': lambda x: x,
            'fingerprint_hasher': lambda x: x,
        }
        request2 = Request("http://www.example.com/", meta=meta)
        fingerprint2 = request_fingerprint(request2)
        assert request1.fingerprint is None
        assert request2.fingerprint is None
        assert fingerprint1 == fingerprint2

    def test_meta_overriders(self):
        meta = {
            'fingerprint_processors': [lambda x, y: x.url],
            'fingerprint_serializer': lambda x: x,
            'fingerprint_hasher': lambda x: x,
        }
        request = Request("http://www.example.com/", meta=meta)
        fingerprint = request_fingerprint(
            request, settings=Settings(), hexadecimal=False)
        assert fingerprint == request.url
        assert request.fingerprint == fingerprint

    def test_settings_overriders(self):
        settings = Settings()
        settings['REQUEST_FINGERPRINT_PROCESSORS'] = [lambda x, y: x.url]
        settings['REQUEST_FINGERPRINT_SERIALIZER'] = lambda x: x
        settings['REQUEST_FINGERPRINT_HASHER'] = lambda x: x
        request = Request("http://www.example.com/")
        fingerprint = request_fingerprint(
            request, settings=settings, hexadecimal=False)
        assert fingerprint == request.url
        assert request.fingerprint == fingerprint

    def test_meta_and_settings_overriders(self):
        meta = {
            'fingerprint_processors': [lambda x, y: x.method],
            'fingerprint_serializer': lambda x: x,
            'fingerprint_hasher': lambda x: x,
        }
        settings = Settings()
        settings['REQUEST_FINGERPRINT_PROCESSORS'] = [lambda x, y: x.url]
        settings['REQUEST_FINGERPRINT_SERIALIZER'] = lambda x: x
        settings['REQUEST_FINGERPRINT_HASHER'] = lambda x: x
        request = Request("http://www.example.com/", meta=meta)
        fingerprint = request_fingerprint(
            request, settings=settings, hexadecimal=False)
        assert fingerprint == request.method
        assert request.fingerprint == fingerprint

    def test_multiple_processors(self):
        meta = {
            'fingerprint_processors': [lambda x, y: x.method,
                                       lambda x, y: y+x.url],
            'fingerprint_serializer': lambda x: x,
            'fingerprint_hasher': lambda x: x,
        }
        request = Request("http://www.example.com/", meta=meta)
        fingerprint = request_fingerprint(
            request, settings=Settings(), hexadecimal=False)
        assert fingerprint == request.method + request.url
        assert request.fingerprint == fingerprint


class RequestFingerprintRecipesTests(unittest.TestCase):
    """Tests for the recipes at docs/topics/request-fingerprinting.rst"""

    def test_include_some_headers(self):
        from functools import partial
        from scrapy.utils.request import process_request_fingerprint
        meta = {
            'fingerprint_processors': [
                partial(process_request_fingerprint, headers={'X-My-Header'})
            ],
        }
        request1 = Request("http://www.example.com/",
                           headers={'X-My-Header': 1},
                           meta=meta)
        request2 = Request("http://www.example.com/",
                           headers={'X-My-Header': 1},
                           meta=meta)
        request3 = Request("http://www.example.com/",
                           headers={'X-My-Header': 2},
                           meta=meta)
        request4 = Request("http://www.example.com/",
                           meta=meta)
        kwargs = dict(settings = Settings(), hexadecimal=False)
        fingerprint1 = request_fingerprint(request1, **kwargs)
        fingerprint2 = request_fingerprint(request2, **kwargs)
        fingerprint3 = request_fingerprint(request3, **kwargs)
        fingerprint4 = request_fingerprint(request4, **kwargs)
        assert fingerprint1 == fingerprint2
        assert fingerprint1 != fingerprint3
        assert fingerprint1 != fingerprint4

    def test_case_insensitive_urls(self):
        from functools import partial
        from w3lib.url import canonicalize_url
        from scrapy.utils.request import process_request_fingerprint
        def url_processor(url):
            return canonicalize_url(url).lower()
        meta = {
            'fingerprint_processors': [
                partial(process_request_fingerprint, url_processor=url_processor),
            ],
        }
        request1 = Request("http://www.example.com/", meta=meta)
        request2 = Request("HTTP://WWW.EXAMPLE.COM/", meta=meta)
        kwargs = dict(settings = Settings(), hexadecimal=False)
        fingerprint1 = request_fingerprint(request1, **kwargs)
        fingerprint2 = request_fingerprint(request2, **kwargs)
        assert fingerprint1 == fingerprint2

    def test_ignore_some_query_string_parameters(self):
        from functools import partial
        from w3lib.url import canonicalize_url, url_query_cleaner
        from scrapy.utils.request import process_request_fingerprint
        def url_processor(url):
            url = canonicalize_url(url)
            parameters = ['parameters', 'to', 'ignore']
            return url_query_cleaner(url, parameterlist=parameters, remove=True)
        meta = {
            'fingerprint_processors': [
                partial(process_request_fingerprint, url_processor=url_processor),
            ],
        }
        request1 = Request("http://www.example.com/?count=1&ignore=1",
                           meta=meta)
        request2 = Request("http://www.example.com/?count=1&ignore=2",
                           meta=meta)
        request3 = Request("http://www.example.com/?count=3&ignore=1",
                           meta=meta)
        kwargs = dict(settings = Settings(), hexadecimal=False)
        fingerprint1 = request_fingerprint(request1, **kwargs)
        fingerprint2 = request_fingerprint(request2, **kwargs)
        fingerprint3 = request_fingerprint(request3, **kwargs)
        assert fingerprint1 == fingerprint2
        assert fingerprint1 != fingerprint3

    def test_old_behavior(self):
        import hashlib
        from w3lib.url import canonicalize_url
        from scrapy.utils.python import to_bytes
        def old_serializer(request):
            method = to_bytes(request.method)
            url = to_bytes(canonicalize_url(request.url))
            body = request.body or b''
            return method + url + body
        meta = {
            'fingerprint_processors': [lambda x, y: x],
            'fingerprint_serializer': old_serializer,
            'fingerprint_hasher': lambda x: hashlib.sha1(x).hexdigest(),
        }
        request1 = Request("https://example.com", meta=meta)
        kwargs = dict(settings = Settings(), hexadecimal=False)
        fingerprint = request_fingerprint(request1, **kwargs)
        assert fingerprint == '6d748741a927b10454c83ac285b002cd239964ea'


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

        r1 = Request("http://www.example.com", method='POST', headers={"Content-type": b"text/html"}, body=b"Some body")
        self.assertEqual(request_httprepr(r1), b'POST / HTTP/1.1\r\nHost: www.example.com\r\nContent-Type: text/html\r\n\r\nSome body')

    def test_request_httprepr_for_non_http_request(self):
        # the representation is not important but it must not fail.
        request_httprepr(Request("file:///tmp/foo.txt"))
        request_httprepr(Request("ftp://localhost/tmp/foo.txt"))


class SHA1HasherTests(unittest.TestCase):

    def test_sha1_hasher(self):
        hashed = b'\x17D\xf5>\x00\xfc#\xbd>Q[)\x8eB\x93d\x85\x06\x1d\xba'
        assert sha1_hasher(b'{"a": 1, "b": 2}') == hashed


if __name__ == "__main__":
    unittest.main()
