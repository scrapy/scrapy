from __future__ import annotations

import json
import random
import re
import shutil
import string
from ipaddress import IPv4Address
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING
from unittest import mock, skipIf
from urllib.parse import urlencode

import pytest
from twisted.internet import reactor
from twisted.internet.defer import (
    CancelledError,
    Deferred,
    DeferredList,
    inlineCallbacks,
)
from twisted.internet.endpoints import SSL4ClientEndpoint, SSL4ServerEndpoint
from twisted.internet.error import TimeoutError
from twisted.internet.ssl import Certificate, PrivateCertificate, optionsForClientTLS
from twisted.trial.unittest import TestCase
from twisted.web.client import URI, ResponseFailed
from twisted.web.http import H2_ENABLED
from twisted.web.http import Request as TxRequest
from twisted.web.server import NOT_DONE_YET, Site
from twisted.web.static import File

from scrapy.http import JsonRequest, Request, Response
from scrapy.settings import Settings
from scrapy.spiders import Spider
from tests.mockserver import LeafResource, Status, ssl_context_factory

if TYPE_CHECKING:
    from twisted.python.failure import Failure


def generate_random_string(size):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=size))


def make_html_body(val):
    response = f"""<html>
<h1>Hello from HTTP2<h1>
<p>{val}</p>
</html>"""
    return bytes(response, "utf-8")


class DummySpider(Spider):
    name = "dummy"
    start_urls: list = []

    def parse(self, response):
        print(response)


class Data:
    SMALL_SIZE = 1024  # 1 KB
    LARGE_SIZE = 1024**2  # 1 MB

    STR_SMALL = generate_random_string(SMALL_SIZE)
    STR_LARGE = generate_random_string(LARGE_SIZE)

    EXTRA_SMALL = generate_random_string(1024 * 15)
    EXTRA_LARGE = generate_random_string((1024**2) * 15)

    HTML_SMALL = make_html_body(STR_SMALL)
    HTML_LARGE = make_html_body(STR_LARGE)

    JSON_SMALL = {"data": STR_SMALL}
    JSON_LARGE = {"data": STR_LARGE}

    DATALOSS = b"Dataloss Content"
    NO_CONTENT_LENGTH = b"This response do not have any content-length header"


class GetDataHtmlSmall(LeafResource):
    def render_GET(self, request: TxRequest):
        request.setHeader("Content-Type", "text/html; charset=UTF-8")
        return Data.HTML_SMALL


class GetDataHtmlLarge(LeafResource):
    def render_GET(self, request: TxRequest):
        request.setHeader("Content-Type", "text/html; charset=UTF-8")
        return Data.HTML_LARGE


class PostDataJsonMixin:
    @staticmethod
    def make_response(request: TxRequest, extra_data: str):
        assert request.content is not None
        response = {
            "request-headers": {},
            "request-body": json.loads(request.content.read()),
            "extra-data": extra_data,
        }
        for k, v in request.requestHeaders.getAllRawHeaders():
            response["request-headers"][str(k, "utf-8")] = str(v[0], "utf-8")

        response_bytes = bytes(json.dumps(response), "utf-8")
        request.setHeader("Content-Type", "application/json; charset=UTF-8")
        request.setHeader("Content-Encoding", "UTF-8")
        return response_bytes


class PostDataJsonSmall(LeafResource, PostDataJsonMixin):
    def render_POST(self, request: TxRequest):
        return self.make_response(request, Data.EXTRA_SMALL)


class PostDataJsonLarge(LeafResource, PostDataJsonMixin):
    def render_POST(self, request: TxRequest):
        return self.make_response(request, Data.EXTRA_LARGE)


class Dataloss(LeafResource):
    def render_GET(self, request: TxRequest):
        request.setHeader(b"Content-Length", b"1024")
        self.deferRequest(request, 0, self._delayed_render, request)
        return NOT_DONE_YET

    @staticmethod
    def _delayed_render(request: TxRequest):
        request.write(Data.DATALOSS)
        request.finish()


class NoContentLengthHeader(LeafResource):
    def render_GET(self, request: TxRequest):
        request.requestHeaders.removeHeader("Content-Length")
        self.deferRequest(request, 0, self._delayed_render, request)
        return NOT_DONE_YET

    @staticmethod
    def _delayed_render(request: TxRequest):
        request.write(Data.NO_CONTENT_LENGTH)
        request.finish()


class TimeoutResponse(LeafResource):
    def render_GET(self, request: TxRequest):
        return NOT_DONE_YET


class QueryParams(LeafResource):
    def render_GET(self, request: TxRequest):
        request.setHeader("Content-Type", "application/json; charset=UTF-8")
        request.setHeader("Content-Encoding", "UTF-8")

        query_params: dict[str, str] = {}
        assert request.args is not None
        for k, v in request.args.items():
            query_params[str(k, "utf-8")] = str(v[0], "utf-8")

        return bytes(json.dumps(query_params), "utf-8")


class RequestHeaders(LeafResource):
    """Sends all the headers received as a response"""

    def render_GET(self, request: TxRequest):
        request.setHeader("Content-Type", "application/json; charset=UTF-8")
        request.setHeader("Content-Encoding", "UTF-8")
        headers = {}
        for k, v in request.requestHeaders.getAllRawHeaders():
            headers[str(k, "utf-8")] = str(v[0], "utf-8")

        return bytes(json.dumps(headers), "utf-8")


def get_client_certificate(
    key_file: Path, certificate_file: Path
) -> PrivateCertificate:
    pem = key_file.read_text(encoding="utf-8") + certificate_file.read_text(
        encoding="utf-8"
    )

    return PrivateCertificate.loadPEM(pem)


@skipIf(not H2_ENABLED, "HTTP/2 support in Twisted is not enabled")
class TestHttps2ClientProtocol(TestCase):
    scheme = "https"
    key_file = Path(__file__).parent / "keys" / "localhost.key"
    certificate_file = Path(__file__).parent / "keys" / "localhost.crt"

    def _init_resource(self):
        self.temp_directory = mkdtemp()
        r = File(self.temp_directory)
        r.putChild(b"get-data-html-small", GetDataHtmlSmall())
        r.putChild(b"get-data-html-large", GetDataHtmlLarge())

        r.putChild(b"post-data-json-small", PostDataJsonSmall())
        r.putChild(b"post-data-json-large", PostDataJsonLarge())

        r.putChild(b"dataloss", Dataloss())
        r.putChild(b"no-content-length-header", NoContentLengthHeader())
        r.putChild(b"status", Status())
        r.putChild(b"query-params", QueryParams())
        r.putChild(b"timeout", TimeoutResponse())
        r.putChild(b"request-headers", RequestHeaders())
        return r

    @inlineCallbacks
    def setUp(self):
        # Initialize resource tree
        root = self._init_resource()
        self.site = Site(root, timeout=None)

        # Start server for testing
        self.hostname = "localhost"
        context_factory = ssl_context_factory(
            str(self.key_file), str(self.certificate_file)
        )

        server_endpoint = SSL4ServerEndpoint(
            reactor, 0, context_factory, interface=self.hostname
        )
        self.server = yield server_endpoint.listen(self.site)
        self.port_number = self.server.getHost().port

        # Connect H2 client with server
        self.client_certificate = get_client_certificate(
            self.key_file, self.certificate_file
        )
        client_options = optionsForClientTLS(
            hostname=self.hostname,
            trustRoot=self.client_certificate,
            acceptableProtocols=[b"h2"],
        )
        uri = URI.fromBytes(bytes(self.get_url("/"), "utf-8"))

        self.conn_closed_deferred = Deferred()
        from scrapy.core.http2.protocol import H2ClientFactory

        h2_client_factory = H2ClientFactory(uri, Settings(), self.conn_closed_deferred)
        client_endpoint = SSL4ClientEndpoint(
            reactor, self.hostname, self.port_number, client_options
        )
        self.client = yield client_endpoint.connect(h2_client_factory)

    @inlineCallbacks
    def tearDown(self):
        if self.client.connected:
            yield self.client.transport.loseConnection()
            yield self.client.transport.abortConnection()
        yield self.server.stopListening()
        shutil.rmtree(self.temp_directory)
        self.conn_closed_deferred = None

    def get_url(self, path):
        """
        :param path: Should have / at the starting compulsorily if not empty
        :return: Complete url
        """
        assert len(path) > 0
        assert path[0] == "/" or path[0] == "&"
        return f"{self.scheme}://{self.hostname}:{self.port_number}{path}"

    def make_request(self, request: Request) -> Deferred:
        return self.client.request(request, DummySpider())

    @staticmethod
    def _check_repeat(get_deferred, count):
        d_list = []
        for _ in range(count):
            d = get_deferred()
            d_list.append(d)

        return DeferredList(d_list, fireOnOneErrback=True)

    def _check_GET(self, request: Request, expected_body, expected_status):
        def check_response(response: Response):
            assert response.status == expected_status
            assert response.body == expected_body
            assert response.request == request

            content_length_header = response.headers.get("Content-Length")
            assert content_length_header is not None
            content_length = int(content_length_header)
            assert len(response.body) == content_length

        d = self.make_request(request)
        d.addCallback(check_response)
        d.addErrback(self.fail)
        return d

    def test_GET_small_body(self):
        request = Request(self.get_url("/get-data-html-small"))
        return self._check_GET(request, Data.HTML_SMALL, 200)

    def test_GET_large_body(self):
        request = Request(self.get_url("/get-data-html-large"))
        return self._check_GET(request, Data.HTML_LARGE, 200)

    def _check_GET_x10(self, *args, **kwargs):
        def get_deferred():
            return self._check_GET(*args, **kwargs)

        return self._check_repeat(get_deferred, 10)

    def test_GET_small_body_x10(self):
        return self._check_GET_x10(
            Request(self.get_url("/get-data-html-small")), Data.HTML_SMALL, 200
        )

    def test_GET_large_body_x10(self):
        return self._check_GET_x10(
            Request(self.get_url("/get-data-html-large")), Data.HTML_LARGE, 200
        )

    def _check_POST_json(
        self,
        request: Request,
        expected_request_body,
        expected_extra_data,
        expected_status: int,
    ):
        d = self.make_request(request)

        def assert_response(response: Response):
            assert response.status == expected_status
            assert response.request == request

            content_length_header = response.headers.get("Content-Length")
            assert content_length_header is not None
            content_length = int(content_length_header)
            assert len(response.body) == content_length

            # Parse the body
            content_encoding_header = response.headers[b"Content-Encoding"]
            assert content_encoding_header is not None
            content_encoding = str(content_encoding_header, "utf-8")
            body = json.loads(str(response.body, content_encoding))
            assert "request-body" in body
            assert "extra-data" in body
            assert "request-headers" in body

            request_body = body["request-body"]
            assert request_body == expected_request_body

            extra_data = body["extra-data"]
            assert extra_data == expected_extra_data

            # Check if headers were sent successfully
            request_headers = body["request-headers"]
            for k, v in request.headers.items():
                k_str = str(k, "utf-8")
                assert k_str in request_headers
                assert request_headers[k_str] == str(v[0], "utf-8")

        d.addCallback(assert_response)
        d.addErrback(self.fail)
        return d

    def test_POST_small_json(self):
        request = JsonRequest(
            url=self.get_url("/post-data-json-small"),
            method="POST",
            data=Data.JSON_SMALL,
        )
        return self._check_POST_json(request, Data.JSON_SMALL, Data.EXTRA_SMALL, 200)

    def test_POST_large_json(self):
        request = JsonRequest(
            url=self.get_url("/post-data-json-large"),
            method="POST",
            data=Data.JSON_LARGE,
        )
        return self._check_POST_json(request, Data.JSON_LARGE, Data.EXTRA_LARGE, 200)

    def _check_POST_json_x10(self, *args, **kwargs):
        def get_deferred():
            return self._check_POST_json(*args, **kwargs)

        return self._check_repeat(get_deferred, 10)

    def test_POST_small_json_x10(self):
        request = JsonRequest(
            url=self.get_url("/post-data-json-small"),
            method="POST",
            data=Data.JSON_SMALL,
        )
        return self._check_POST_json_x10(
            request, Data.JSON_SMALL, Data.EXTRA_SMALL, 200
        )

    def test_POST_large_json_x10(self):
        request = JsonRequest(
            url=self.get_url("/post-data-json-large"),
            method="POST",
            data=Data.JSON_LARGE,
        )
        return self._check_POST_json_x10(
            request, Data.JSON_LARGE, Data.EXTRA_LARGE, 200
        )

    @inlineCallbacks
    def test_invalid_negotiated_protocol(self):
        with mock.patch(
            "scrapy.core.http2.protocol.PROTOCOL_NAME", return_value=b"not-h2"
        ):
            request = Request(url=self.get_url("/status?n=200"))
            with pytest.raises(ResponseFailed):
                yield self.make_request(request)

    def test_cancel_request(self):
        request = Request(url=self.get_url("/get-data-html-large"))

        def assert_response(response: Response):
            assert response.status == 499
            assert response.request == request

        d = self.make_request(request)
        d.addCallback(assert_response)
        d.addErrback(self.fail)
        d.cancel()

        return d

    def test_download_maxsize_exceeded(self):
        request = Request(
            url=self.get_url("/get-data-html-large"), meta={"download_maxsize": 1000}
        )

        def assert_cancelled_error(failure):
            assert isinstance(failure.value, CancelledError)
            error_pattern = re.compile(
                rf"Cancelling download of {request.url}: received response "
                rf"size \(\d*\) larger than download max size \(1000\)"
            )
            assert len(re.findall(error_pattern, str(failure.value))) == 1

        d = self.make_request(request)
        d.addCallback(self.fail)
        d.addErrback(assert_cancelled_error)
        return d

    def test_received_dataloss_response(self):
        """In case when value of Header Content-Length != len(Received Data)
        ProtocolError is raised"""
        request = Request(url=self.get_url("/dataloss"))

        def assert_failure(failure: Failure):
            assert len(failure.value.reasons) > 0
            from h2.exceptions import InvalidBodyLengthError

            assert any(
                isinstance(error, InvalidBodyLengthError)
                for error in failure.value.reasons
            )

        d = self.make_request(request)
        d.addCallback(self.fail)
        d.addErrback(assert_failure)
        return d

    def test_missing_content_length_header(self):
        request = Request(url=self.get_url("/no-content-length-header"))

        def assert_content_length(response: Response):
            assert response.status == 200
            assert response.body == Data.NO_CONTENT_LENGTH
            assert response.request == request
            assert "Content-Length" not in response.headers

        d = self.make_request(request)
        d.addCallback(assert_content_length)
        d.addErrback(self.fail)
        return d

    @inlineCallbacks
    def _check_log_warnsize(self, request, warn_pattern, expected_body):
        with self.assertLogs("scrapy.core.http2.stream", level="WARNING") as cm:
            response = yield self.make_request(request)
            assert response.status == 200
            assert response.request == request
            assert response.body == expected_body

            # Check the warning is raised only once for this request
            assert sum(len(re.findall(warn_pattern, log)) for log in cm.output) == 1

    @inlineCallbacks
    def test_log_expected_warnsize(self):
        request = Request(
            url=self.get_url("/get-data-html-large"), meta={"download_warnsize": 1000}
        )
        warn_pattern = re.compile(
            rf"Expected response size \(\d*\) larger than "
            rf"download warn size \(1000\) in request {request}"
        )

        yield self._check_log_warnsize(request, warn_pattern, Data.HTML_LARGE)

    @inlineCallbacks
    def test_log_received_warnsize(self):
        request = Request(
            url=self.get_url("/no-content-length-header"),
            meta={"download_warnsize": 10},
        )
        warn_pattern = re.compile(
            rf"Received more \(\d*\) bytes than download "
            rf"warn size \(10\) in request {request}"
        )

        yield self._check_log_warnsize(request, warn_pattern, Data.NO_CONTENT_LENGTH)

    def test_max_concurrent_streams(self):
        """Send 500 requests at one to check if we can handle
        very large number of request.
        """

        def get_deferred():
            return self._check_GET(
                Request(self.get_url("/get-data-html-small")), Data.HTML_SMALL, 200
            )

        return self._check_repeat(get_deferred, 500)

    def test_inactive_stream(self):
        """Here we send 110 requests considering the MAX_CONCURRENT_STREAMS
        by default is 100. After sending the first 100 requests we close the
        connection."""
        d_list = []

        def assert_inactive_stream(failure):
            assert failure.check(ResponseFailed) is not None
            from scrapy.core.http2.stream import InactiveStreamClosed

            assert any(
                isinstance(e, InactiveStreamClosed) for e in failure.value.reasons
            )

        # Send 100 request (we do not check the result)
        for _ in range(100):
            d = self.make_request(Request(self.get_url("/get-data-html-small")))
            d.addBoth(lambda _: None)
            d_list.append(d)

        # Now send 10 extra request and save the response deferred in a list
        for _ in range(10):
            d = self.make_request(Request(self.get_url("/get-data-html-small")))
            d.addCallback(self.fail)
            d.addErrback(assert_inactive_stream)
            d_list.append(d)

        # Close the connection now to fire all the extra 10 requests errback
        # with InactiveStreamClosed
        self.client.transport.loseConnection()

        return DeferredList(d_list, consumeErrors=True, fireOnOneErrback=True)

    def test_invalid_request_type(self):
        with pytest.raises(TypeError):
            self.make_request("https://InvalidDataTypePassed.com")

    def test_query_parameters(self):
        params = {
            "a": generate_random_string(20),
            "b": generate_random_string(20),
            "c": generate_random_string(20),
            "d": generate_random_string(20),
        }
        request = Request(self.get_url(f"/query-params?{urlencode(params)}"))

        def assert_query_params(response: Response):
            content_encoding_header = response.headers[b"Content-Encoding"]
            assert content_encoding_header is not None
            content_encoding = str(content_encoding_header, "utf-8")
            data = json.loads(str(response.body, content_encoding))
            assert data == params

        d = self.make_request(request)
        d.addCallback(assert_query_params)
        d.addErrback(self.fail)

        return d

    def test_status_codes(self):
        def assert_response_status(response: Response, expected_status: int):
            assert response.status == expected_status

        d_list = []
        for status in [200, 404]:
            request = Request(self.get_url(f"/status?n={status}"))
            d = self.make_request(request)
            d.addCallback(assert_response_status, status)
            d.addErrback(self.fail)
            d_list.append(d)

        return DeferredList(d_list, fireOnOneErrback=True)

    def test_response_has_correct_certificate_ip_address(self):
        request = Request(self.get_url("/status?n=200"))

        def assert_metadata(response: Response):
            assert response.request == request
            assert isinstance(response.certificate, Certificate)
            assert response.certificate.original is not None
            assert (
                response.certificate.getIssuer() == self.client_certificate.getIssuer()
            )
            assert response.certificate.getPublicKey().matches(
                self.client_certificate.getPublicKey()
            )

            assert isinstance(response.ip_address, IPv4Address)
            assert str(response.ip_address) == "127.0.0.1"

        d = self.make_request(request)
        d.addCallback(assert_metadata)
        d.addErrback(self.fail)

        return d

    def _check_invalid_netloc(self, url):
        request = Request(url)

        def assert_invalid_hostname(failure: Failure):
            from scrapy.core.http2.stream import InvalidHostname

            assert failure.check(InvalidHostname) is not None
            error_msg = str(failure.value)
            assert "localhost" in error_msg
            assert "127.0.0.1" in error_msg
            assert str(request) in error_msg

        d = self.make_request(request)
        d.addCallback(self.fail)
        d.addErrback(assert_invalid_hostname)
        return d

    def test_invalid_hostname(self):
        return self._check_invalid_netloc("https://notlocalhost.notlocalhostdomain")

    def test_invalid_host_port(self):
        port = self.port_number + 1
        return self._check_invalid_netloc(f"https://127.0.0.1:{port}")

    def test_connection_stays_with_invalid_requests(self):
        d_list = [
            self.test_invalid_hostname(),
            self.test_invalid_host_port(),
            self.test_GET_small_body(),
            self.test_POST_small_json(),
        ]

        return DeferredList(d_list, fireOnOneErrback=True)

    def test_connection_timeout(self):
        request = Request(self.get_url("/timeout"))
        d = self.make_request(request)

        # Update the timer to 1s to test connection timeout
        self.client.setTimeout(1)

        def assert_timeout_error(failure: Failure):
            for err in failure.value.reasons:
                from scrapy.core.http2.protocol import H2ClientProtocol

                if isinstance(err, TimeoutError):
                    assert (
                        f"Connection was IDLE for more than {H2ClientProtocol.IDLE_TIMEOUT}s"
                        in str(err)
                    )
                    break
            else:
                pytest.fail("No TimeoutError raised.")

        d.addCallback(self.fail)
        d.addErrback(assert_timeout_error)
        return d

    def test_request_headers_received(self):
        request = Request(
            self.get_url("/request-headers"),
            headers={"header-1": "header value 1", "header-2": "header value 2"},
        )
        d = self.make_request(request)

        def assert_request_headers(response: Response):
            assert response.status == 200
            assert response.request == request

            response_headers = json.loads(str(response.body, "utf-8"))
            assert isinstance(response_headers, dict)
            for k, v in request.headers.items():
                k, v = str(k, "utf-8"), str(v[0], "utf-8")
                assert k in response_headers
                assert v == response_headers[k]

        d.addErrback(self.fail)
        d.addCallback(assert_request_headers)
        return d
