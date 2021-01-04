import unittest
from ipaddress import ip_address
from pathlib import Path

from scrapy.http.request import Request
from scrapy.http.response import Response
from scrapy.http.response.html import HtmlResponse

from twisted.internet.ssl import Certificate


class CustomResponse(Response):
    pass


class ResponseSerializationTest(unittest.TestCase):

    def _assert_serializes_ok(self, response):
        d = response.to_dict()
        response2 = Response.from_dict(d)
        self._assert_same_response(response, response2)

    def _assert_same_response(self, r1, r2):
        self.assertEqual(r1.__class__, r2.__class__)
        self.assertEqual(r1.url, r2.url)
        self.assertEqual(r1.status, r2.status)
        self.assertEqual(r1.headers, r2.headers)
        self.assertEqual(r1.body, r2.body)
        self.assertEqual(r1.flags, r2.flags)
        self.assertEqual(r1.request, r2.request)
        self.assertEqual(r1.certificate, r2.certificate)
        self.assertEqual(r1.ip_address, r2.ip_address)
        self.assertEqual(r1.protocol, r2.protocol)

    def test_basic(self):
        r = Response("http://www.example.com")
        self._assert_serializes_ok(r)

    def test_all_attributes(self):
        cert_path = Path(__file__).parent / "keys/localhost.crt"
        cert_pem = cert_path.read_text()
        response = Response(
            url="http://www.example.com",
            status=201,
            headers={"foo": "bar", "some": "header"},
            body=b"Lorem Ipsum",
            flags=["test", "flag"],
            request=Request("https://example.com"),
            certificate=Certificate.loadPEM(cert_pem),
            ip_address=ip_address("1.2.3.4"),
            protocol="HTTP/99",
        )
        self._assert_serializes_ok(response)

    def test_request_class(self):
        r = HtmlResponse("http://www.example.com")
        self._assert_serializes_ok(r)
        r = CustomResponse("http://www.example.com")
        self._assert_serializes_ok(r)
