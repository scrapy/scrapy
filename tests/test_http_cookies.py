from urllib.parse import urlparse
from unittest import TestCase

from scrapy.http import Request, Response
from scrapy.http.cookies import WrappedRequest, WrappedResponse


class WrappedRequestTest(TestCase):

    def setUp(self):
        self.request = Request("http://www.example.com/page.html",
                               headers={"Content-Type": "text/html"})
        self.wrapped = WrappedRequest(self.request)

    def test_get_full_url(self):
        self.assertEqual(self.wrapped.get_full_url(), self.request.url)
        self.assertEqual(self.wrapped.full_url, self.request.url)

    def test_get_host(self):
        self.assertEqual(self.wrapped.get_host(), urlparse(self.request.url).netloc)
        self.assertEqual(self.wrapped.host, urlparse(self.request.url).netloc)

    def test_get_type(self):
        self.assertEqual(self.wrapped.get_type(), urlparse(self.request.url).scheme)
        self.assertEqual(self.wrapped.type, urlparse(self.request.url).scheme)

    def test_is_unverifiable(self):
        self.assertFalse(self.wrapped.is_unverifiable())
        self.assertFalse(self.wrapped.unverifiable)

    def test_is_unverifiable2(self):
        self.request.meta['is_unverifiable'] = True
        self.assertTrue(self.wrapped.is_unverifiable())
        self.assertTrue(self.wrapped.unverifiable)

    def test_get_origin_req_host(self):
        self.assertEqual(self.wrapped.get_origin_req_host(), 'www.example.com')
        self.assertEqual(self.wrapped.origin_req_host, 'www.example.com')

    def test_has_header(self):
        self.assertTrue(self.wrapped.has_header('content-type'))
        self.assertFalse(self.wrapped.has_header('xxxxx'))

    def test_get_header(self):
        self.assertEqual(self.wrapped.get_header('content-type'), 'text/html')
        self.assertEqual(self.wrapped.get_header('xxxxx', 'def'), 'def')

    def test_header_items(self):
        self.assertEqual(self.wrapped.header_items(),
                         [('Content-Type', ['text/html'])])

    def test_add_unredirected_header(self):
        self.wrapped.add_unredirected_header('hello', 'world')
        self.assertEqual(self.request.headers['hello'], b'world')


class WrappedResponseTest(TestCase):

    def setUp(self):
        self.response = Response("http://www.example.com/page.html",
                                 headers={"Content-TYpe": "text/html"})
        self.wrapped = WrappedResponse(self.response)

    def test_info(self):
        self.assertIs(self.wrapped.info(), self.wrapped)

    def test_getheaders(self):
        self.assertEqual(self.wrapped.getheaders('content-type'), ['text/html'])

    def test_get_all(self):
        # get_all result must be native string
        self.assertEqual(self.wrapped.get_all('content-type'), ['text/html'])
