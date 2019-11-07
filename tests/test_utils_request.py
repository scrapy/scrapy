import unittest

from w3lib.url import canonicalize_url

from scrapy.http import Request
from scrapy.utils.request import (
    default_request_key_builder, default_request_key_hasher,
    request_authenticate, request_httprepr, RequestKeyBuilder)


class DefaultRequestKeyBuilderTest(unittest.TestCase):

    def test_attributes_no_value(self):
        r1 = Request('http://www.example.com/hnnoticiaj1.aspx?78132,199')
        r2 = Request('http://www.example.com/hnnoticiaj1.aspx?78160,199')
        self.assertNotEqual(default_request_key_builder(r1),
                            default_request_key_builder(r2))

    def test_attributes_order(self):
        r1 = Request("http://www.example.com/query?id=111&cat=222")
        r2 = Request("http://www.example.com/query?cat=222&id=111")
        self.assertEqual(default_request_key_builder(r1),
                         default_request_key_builder(r1))
        self.assertEqual(default_request_key_builder(r1),
                         default_request_key_builder(r2))

    def test_body(self):
        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com", body=b'request body')
        self.assertNotEqual(default_request_key_builder(r1),
                            default_request_key_builder(r2))

    def test_fragments(self):
        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com#a")
        r3 = Request("http://www.example.com#b")
        self.assertEqual(default_request_key_builder(r1),
                         default_request_key_builder(r2))
        self.assertEqual(default_request_key_builder(r2),
                         default_request_key_builder(r3))
        self.assertEqual(default_request_key_builder(r1),
                         default_request_key_builder(r3))

    def test_headers(self):
        r1 = Request("http://www.example.com/members/offers.html")
        r2 = Request("http://www.example.com/members/offers.html")
        r2.headers['SESSIONID'] = b"somehash"
        self.assertEqual(default_request_key_builder(r1),
                         default_request_key_builder(r2))

    def test_meta(self):
        r1 = Request("https://example.com")
        r2 = r1.replace(meta={'a': 'b'})
        self.assertEqual(default_request_key_builder(r1),
                         default_request_key_builder(r2))

    def test_method(self):
        r1 = Request("http://www.example.com")
        r2 = Request("http://www.example.com", method='POST')
        self.assertNotEqual(default_request_key_builder(r1),
                            default_request_key_builder(r2))


class RequestKeyBuilderTest(unittest.TestCase):

    def test_cache(self):

        class Counter:

            def __init__(self):
                self.count = 0

            def __call__(self, data, request):
                self.count += 1
                return default_request_key_hasher(data, request)

        counter = Counter()

        builder = RequestKeyBuilder(post_processor=counter)
        request = Request('https://example.com')

        builder(request)
        builder(request)

        assert counter.count == 1

    def test_cache_after_copy(self):
        r1 = Request("http://www.example.com/1")
        r2 = r1.replace(url="http://www.example.com/2")
        self.assertNotEqual(default_request_key_builder(r1),
                            default_request_key_builder(r2))

    def test_headers_builder_order(self):
        request = Request("http://www.example.com/",
                          headers={'a': 'b', 'c': 'd'})

        builder1 = RequestKeyBuilder(headers=['a', 'c'])
        builder2 = RequestKeyBuilder(headers=['c', 'a'])

        self.assertEqual(builder1(request), builder2(request))

    def test_headers_case(self):
        r1 = Request("http://www.example.com/", headers={'a': 'b'})
        r2 = r1.replace(headers={'A': 'b'})

        builder = RequestKeyBuilder(headers=['a'])

        self.assertEqual(builder(r1), builder(r2))

    def test_headers_differ(self):
        r1 = Request("http://www.example.com/")
        r2 = r1.replace(headers={'a': 'b'})

        builder1 = default_request_key_builder
        builder2 = RequestKeyBuilder(headers=['a'])

        self.assertNotEqual(builder1(r2), builder2(r2))
        self.assertNotEqual(builder2(r1), builder2(r2))

    def test_headers_order(self):
        r1 = Request("http://www.example.com/", headers={'a': 'b', 'c': 'd'})
        r2 = r1.replace(headers={'c': 'd', 'a': 'b'})

        builder = RequestKeyBuilder(headers=['a', 'c'])

        self.assertEqual(builder(r1), builder(r2))

    def test_headers_same_key_if_none(self):
        request = Request("http://www.example.com/")

        builder1 = default_request_key_builder
        builder2 = RequestKeyBuilder(headers=['a'])

        self.assertEqual(builder1(request), builder2(request))

    def test_meta_builder_order(self):
        request = Request("http://www.example.com/",
                          meta={'a': 'b', 'c': 'd'})

        builder1 = RequestKeyBuilder(meta=['a', 'c'])
        builder2 = RequestKeyBuilder(meta=['c', 'a'])

        self.assertEqual(builder1(request), builder2(request))

    def test_meta_case(self):
        r1 = Request("http://www.example.com/", meta={'a': 'b'})
        r2 = r1.replace(meta={'A': 'b'})

        builder = RequestKeyBuilder(meta=['a'])

        self.assertNotEqual(builder(r1), builder(r2))

    def test_meta_differ(self):
        r1 = Request("http://www.example.com/")
        r2 = r1.replace(meta={'a': 'b'})

        builder1 = default_request_key_builder
        builder2 = RequestKeyBuilder(meta=['a'])

        self.assertNotEqual(builder1(r2), builder2(r2))
        self.assertNotEqual(builder2(r1), builder2(r2))

    def test_meta_order(self):
        r1 = Request("http://www.example.com/", meta={'a': 'b', 'c': 'd'})
        r2 = r1.replace(meta={'c': 'd', 'a': 'b'})

        builder = RequestKeyBuilder(meta=['a', 'c'])

        self.assertEqual(builder(r1), builder(r2))

    def test_meta_same_key_if_none(self):
        request = Request("http://www.example.com/")

        builder1 = default_request_key_builder
        builder2 = RequestKeyBuilder(meta=['a'])

        self.assertEqual(builder1(request), builder2(request))

    def test_url_processor_fragments(self):
        r1 = Request("http://www.example.com/test.html")
        r2 = Request("http://www.example.com/test.html#fragment")

        def url_processor(url):
            return canonicalize_url(url, keep_fragments=True)

        builder = RequestKeyBuilder(url_processor=url_processor)

        self.assertEqual(default_request_key_builder(r1), builder(r1))
        self.assertNotEqual(default_request_key_builder(r2), builder(r2))
        self.assertNotEqual(builder(r1), builder(r2))


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


if __name__ == "__main__":
    unittest.main()
