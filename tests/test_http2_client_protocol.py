from __future__ import annotations

import json
import random
import re
import string
from ipaddress import IPv4Address
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast
from unittest import mock
from urllib.parse import urlencode

import pytest
from pytest_twisted import async_yield_fixture
from twisted.internet.defer import (
    CancelledError,
    Deferred,
    DeferredList,
    inlineCallbacks,
)
from twisted.internet.endpoints import SSL4ClientEndpoint, SSL4ServerEndpoint
from twisted.internet.error import TimeoutError as TxTimeoutError
from twisted.internet.ssl import Certificate, PrivateCertificate, optionsForClientTLS
from twisted.web.client import URI, ResponseFailed
from twisted.web.http import H2_ENABLED
from twisted.web.http import Request as TxRequest
from twisted.web.server import NOT_DONE_YET, Site
from twisted.web.static import File

from scrapy.http import JsonRequest, Request, Response
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from tests.mockserver import LeafResource, Status, ssl_context_factory

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Generator

    from scrapy.core.http2.protocol import H2ClientProtocol


def generate_random_string(size: int) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=size))


def make_html_body(val: str) -> bytes:
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
    def make_response(request: TxRequest, extra_data: str) -> bytes:
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


def make_request_dfd(client: H2ClientProtocol, request: Request) -> Deferred[Response]:
    return client.request(request, DummySpider())


async def make_request(client: H2ClientProtocol, request: Request) -> Response:
    return await maybe_deferred_to_future(make_request_dfd(client, request))


@pytest.mark.skipif(not H2_ENABLED, reason="HTTP/2 support in Twisted is not enabled")
class TestHttps2ClientProtocol:
    scheme = "https"
    host = "localhost"
    key_file = Path(__file__).parent / "keys" / "localhost.key"
    certificate_file = Path(__file__).parent / "keys" / "localhost.crt"

    @pytest.fixture
    def site(self, tmp_path):
        r = File(str(tmp_path))
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
        return Site(r, timeout=None)

    @async_yield_fixture
    async def server_port(self, site: Site) -> AsyncGenerator[int]:
        from twisted.internet import reactor

        context_factory = ssl_context_factory(
            str(self.key_file), str(self.certificate_file)
        )
        server_endpoint = SSL4ServerEndpoint(
            reactor, 0, context_factory, interface=self.host
        )
        server = await server_endpoint.listen(site)

        yield server.getHost().port

        await server.stopListening()

    @pytest.fixture
    def client_certificate(self) -> PrivateCertificate:
        pem = self.key_file.read_text(
            encoding="utf-8"
        ) + self.certificate_file.read_text(encoding="utf-8")
        return PrivateCertificate.loadPEM(pem)

    @async_yield_fixture
    async def client(
        self, server_port: int, client_certificate: PrivateCertificate
    ) -> AsyncGenerator[H2ClientProtocol]:
        from twisted.internet import reactor

        from scrapy.core.http2.protocol import H2ClientFactory  # noqa: PLC0415

        client_options = optionsForClientTLS(
            hostname=self.host,
            trustRoot=client_certificate,
            acceptableProtocols=[b"h2"],
        )
        uri = URI.fromBytes(bytes(self.get_url(server_port, "/"), "utf-8"))
        h2_client_factory = H2ClientFactory(uri, Settings(), Deferred())
        client_endpoint = SSL4ClientEndpoint(
            reactor, self.host, server_port, client_options
        )
        client = await client_endpoint.connect(h2_client_factory)

        yield client

        if client.connected:
            client.transport.loseConnection()
            client.transport.abortConnection()

    def get_url(self, portno: int, path: str) -> str:
        """
        :param path: Should have / at the starting compulsorily if not empty
        :return: Complete url
        """
        assert len(path) > 0
        assert path[0] == "/" or path[0] == "&"
        return f"{self.scheme}://{self.host}:{portno}{path}"

    @staticmethod
    async def _check_repeat(
        get_coro: Callable[[], Coroutine[Any, Any, None]], count: int
    ) -> None:
        d_list = []
        for _ in range(count):
            d = deferred_from_coro(get_coro())
            d_list.append(d)

        await maybe_deferred_to_future(DeferredList(d_list, fireOnOneErrback=True))

    async def _check_GET(
        self,
        client: H2ClientProtocol,
        request: Request,
        expected_body: bytes,
        expected_status: int,
    ) -> None:
        response = await make_request(client, request)
        assert response.status == expected_status
        assert response.body == expected_body
        assert response.request == request

        content_length_header = response.headers.get("Content-Length")
        assert content_length_header is not None
        content_length = int(content_length_header)
        assert len(response.body) == content_length

    @deferred_f_from_coro_f
    async def test_GET_small_body(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = Request(self.get_url(server_port, "/get-data-html-small"))
        await self._check_GET(client, request, Data.HTML_SMALL, 200)

    @deferred_f_from_coro_f
    async def test_GET_large_body(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = Request(self.get_url(server_port, "/get-data-html-large"))
        await self._check_GET(client, request, Data.HTML_LARGE, 200)

    async def _check_GET_x10(
        self,
        client: H2ClientProtocol,
        request: Request,
        expected_body: bytes,
        expected_status: int,
    ) -> None:
        async def get_coro() -> None:
            await self._check_GET(client, request, expected_body, expected_status)

        await self._check_repeat(get_coro, 10)

    @deferred_f_from_coro_f
    async def test_GET_small_body_x10(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        await self._check_GET_x10(
            client,
            Request(self.get_url(server_port, "/get-data-html-small")),
            Data.HTML_SMALL,
            200,
        )

    @deferred_f_from_coro_f
    async def test_GET_large_body_x10(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        await self._check_GET_x10(
            client,
            Request(self.get_url(server_port, "/get-data-html-large")),
            Data.HTML_LARGE,
            200,
        )

    @staticmethod
    async def _check_POST_json(
        client: H2ClientProtocol,
        request: Request,
        expected_request_body: dict[str, str],
        expected_extra_data: str,
        expected_status: int,
    ) -> None:
        response = await make_request(client, request)

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

    @deferred_f_from_coro_f
    async def test_POST_small_json(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = JsonRequest(
            url=self.get_url(server_port, "/post-data-json-small"),
            method="POST",
            data=Data.JSON_SMALL,
        )
        await self._check_POST_json(
            client, request, Data.JSON_SMALL, Data.EXTRA_SMALL, 200
        )

    @deferred_f_from_coro_f
    async def test_POST_large_json(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = JsonRequest(
            url=self.get_url(server_port, "/post-data-json-large"),
            method="POST",
            data=Data.JSON_LARGE,
        )
        await self._check_POST_json(
            client, request, Data.JSON_LARGE, Data.EXTRA_LARGE, 200
        )

    async def _check_POST_json_x10(self, *args, **kwargs):
        async def get_coro() -> None:
            await self._check_POST_json(*args, **kwargs)

        await self._check_repeat(get_coro, 10)

    @deferred_f_from_coro_f
    async def test_POST_small_json_x10(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = JsonRequest(
            url=self.get_url(server_port, "/post-data-json-small"),
            method="POST",
            data=Data.JSON_SMALL,
        )
        await self._check_POST_json_x10(
            client, request, Data.JSON_SMALL, Data.EXTRA_SMALL, 200
        )

    @deferred_f_from_coro_f
    async def test_POST_large_json_x10(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = JsonRequest(
            url=self.get_url(server_port, "/post-data-json-large"),
            method="POST",
            data=Data.JSON_LARGE,
        )
        await self._check_POST_json_x10(
            client, request, Data.JSON_LARGE, Data.EXTRA_LARGE, 200
        )

    @inlineCallbacks
    def test_invalid_negotiated_protocol(
        self, server_port: int, client: H2ClientProtocol
    ) -> Generator[Deferred[Any], Any, None]:
        with mock.patch(
            "scrapy.core.http2.protocol.PROTOCOL_NAME", return_value=b"not-h2"
        ):
            request = Request(url=self.get_url(server_port, "/status?n=200"))
            with pytest.raises(ResponseFailed):
                yield make_request_dfd(client, request)

    @inlineCallbacks
    def test_cancel_request(
        self, server_port: int, client: H2ClientProtocol
    ) -> Generator[Deferred[Any], Any, None]:
        request = Request(url=self.get_url(server_port, "/get-data-html-large"))
        d = make_request_dfd(client, request)
        d.cancel()
        response = cast("Response", (yield d))
        assert response.status == 499
        assert response.request == request

    @deferred_f_from_coro_f
    async def test_download_maxsize_exceeded(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = Request(
            url=self.get_url(server_port, "/get-data-html-large"),
            meta={"download_maxsize": 1000},
        )
        with pytest.raises(CancelledError) as exc_info:
            await make_request(client, request)
        error_pattern = re.compile(
            rf"Cancelling download of {request.url}: received response "
            rf"size \(\d*\) larger than download max size \(1000\)"
        )
        assert len(re.findall(error_pattern, str(exc_info.value))) == 1

    @inlineCallbacks
    def test_received_dataloss_response(
        self, server_port: int, client: H2ClientProtocol
    ) -> Generator[Deferred[Any], Any, None]:
        """In case when value of Header Content-Length != len(Received Data)
        ProtocolError is raised"""
        from h2.exceptions import InvalidBodyLengthError  # noqa: PLC0415

        request = Request(url=self.get_url(server_port, "/dataloss"))
        with pytest.raises(ResponseFailed) as exc_info:
            yield make_request_dfd(client, request)
        assert len(exc_info.value.reasons) > 0
        assert any(
            isinstance(error, InvalidBodyLengthError)
            for error in exc_info.value.reasons
        )

    @deferred_f_from_coro_f
    async def test_missing_content_length_header(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = Request(url=self.get_url(server_port, "/no-content-length-header"))
        response = await make_request(client, request)
        assert response.status == 200
        assert response.body == Data.NO_CONTENT_LENGTH
        assert response.request == request
        assert "Content-Length" not in response.headers

    async def _check_log_warnsize(
        self,
        client: H2ClientProtocol,
        request: Request,
        warn_pattern: re.Pattern[str],
        expected_body: bytes,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level("WARNING", "scrapy.core.http2.stream"):
            response = await make_request(client, request)
        assert response.status == 200
        assert response.request == request
        assert response.body == expected_body

        # Check the warning is raised only once for this request
        assert len(re.findall(warn_pattern, caplog.text)) == 1

    @deferred_f_from_coro_f
    async def test_log_expected_warnsize(
        self,
        server_port: int,
        client: H2ClientProtocol,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        request = Request(
            url=self.get_url(server_port, "/get-data-html-large"),
            meta={"download_warnsize": 1000},
        )
        warn_pattern = re.compile(
            rf"Expected response size \(\d*\) larger than "
            rf"download warn size \(1000\) in request {request}"
        )

        await self._check_log_warnsize(
            client, request, warn_pattern, Data.HTML_LARGE, caplog
        )

    @deferred_f_from_coro_f
    async def test_log_received_warnsize(
        self,
        server_port: int,
        client: H2ClientProtocol,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        request = Request(
            url=self.get_url(server_port, "/no-content-length-header"),
            meta={"download_warnsize": 10},
        )
        warn_pattern = re.compile(
            rf"Received more \(\d*\) bytes than download "
            rf"warn size \(10\) in request {request}"
        )

        await self._check_log_warnsize(
            client, request, warn_pattern, Data.NO_CONTENT_LENGTH, caplog
        )

    @deferred_f_from_coro_f
    async def test_max_concurrent_streams(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        """Send 500 requests at one to check if we can handle
        very large number of request.
        """

        async def get_coro() -> None:
            await self._check_GET(
                client,
                Request(self.get_url(server_port, "/get-data-html-small")),
                Data.HTML_SMALL,
                200,
            )

        await self._check_repeat(get_coro, 500)

    @inlineCallbacks
    def test_inactive_stream(
        self, server_port: int, client: H2ClientProtocol
    ) -> Generator[Deferred[Any], Any, None]:
        """Here we send 110 requests considering the MAX_CONCURRENT_STREAMS
        by default is 100. After sending the first 100 requests we close the
        connection."""
        d_list = []

        def assert_inactive_stream(failure):
            assert failure.check(ResponseFailed) is not None

            from scrapy.core.http2.stream import InactiveStreamClosed  # noqa: PLC0415

            assert any(
                isinstance(e, InactiveStreamClosed) for e in failure.value.reasons
            )

        # Send 100 request (we do not check the result)
        for _ in range(100):
            d = make_request_dfd(
                client, Request(self.get_url(server_port, "/get-data-html-small"))
            )
            d.addBoth(lambda _: None)
            d_list.append(d)

        # Now send 10 extra request and save the response deferred in a list
        for _ in range(10):
            d = make_request_dfd(
                client, Request(self.get_url(server_port, "/get-data-html-small"))
            )
            d.addCallback(lambda _: pytest.fail("This request should have failed"))
            d.addErrback(assert_inactive_stream)
            d_list.append(d)

        # Close the connection now to fire all the extra 10 requests errback
        # with InactiveStreamClosed
        assert client.transport
        client.transport.loseConnection()

        yield DeferredList(d_list, consumeErrors=True, fireOnOneErrback=True)

    @deferred_f_from_coro_f
    async def test_invalid_request_type(self, client: H2ClientProtocol):
        with pytest.raises(TypeError):
            await make_request(client, "https://InvalidDataTypePassed.com")  # type: ignore[arg-type]

    @deferred_f_from_coro_f
    async def test_query_parameters(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        params = {
            "a": generate_random_string(20),
            "b": generate_random_string(20),
            "c": generate_random_string(20),
            "d": generate_random_string(20),
        }
        request = Request(
            self.get_url(server_port, f"/query-params?{urlencode(params)}")
        )
        response = await make_request(client, request)
        content_encoding_header = response.headers[b"Content-Encoding"]
        assert content_encoding_header is not None
        content_encoding = str(content_encoding_header, "utf-8")
        data = json.loads(str(response.body, content_encoding))
        assert data == params

    @deferred_f_from_coro_f
    async def test_status_codes(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        for status in [200, 404]:
            request = Request(self.get_url(server_port, f"/status?n={status}"))
            response = await make_request(client, request)
            assert response.status == status

    @deferred_f_from_coro_f
    async def test_response_has_correct_certificate_ip_address(
        self,
        server_port: int,
        client: H2ClientProtocol,
        client_certificate: PrivateCertificate,
    ) -> None:
        request = Request(self.get_url(server_port, "/status?n=200"))
        response = await make_request(client, request)
        assert response.request == request
        assert isinstance(response.certificate, Certificate)
        assert response.certificate.original is not None
        assert response.certificate.getIssuer() == client_certificate.getIssuer()
        assert response.certificate.getPublicKey().matches(
            client_certificate.getPublicKey()
        )
        assert isinstance(response.ip_address, IPv4Address)
        assert str(response.ip_address) == "127.0.0.1"

    @staticmethod
    async def _check_invalid_netloc(client: H2ClientProtocol, url: str) -> None:
        from scrapy.core.http2.stream import InvalidHostname  # noqa: PLC0415

        request = Request(url)
        with pytest.raises(InvalidHostname) as exc_info:
            await make_request(client, request)
        error_msg = str(exc_info.value)
        assert "localhost" in error_msg
        assert "127.0.0.1" in error_msg
        assert str(request) in error_msg

    @deferred_f_from_coro_f
    async def test_invalid_hostname(self, client: H2ClientProtocol) -> None:
        await self._check_invalid_netloc(
            client, "https://notlocalhost.notlocalhostdomain"
        )

    @deferred_f_from_coro_f
    async def test_invalid_host_port(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        port = server_port + 1
        await self._check_invalid_netloc(client, f"https://127.0.0.1:{port}")

    @deferred_f_from_coro_f
    async def test_connection_stays_with_invalid_requests(
        self, server_port: int, client: H2ClientProtocol
    ):
        await maybe_deferred_to_future(self.test_invalid_hostname(client))
        await maybe_deferred_to_future(self.test_invalid_host_port(server_port, client))
        await maybe_deferred_to_future(self.test_GET_small_body(server_port, client))
        await maybe_deferred_to_future(self.test_POST_small_json(server_port, client))

    @inlineCallbacks
    def test_connection_timeout(
        self, server_port: int, client: H2ClientProtocol
    ) -> Generator[Deferred[Any], Any, None]:
        request = Request(self.get_url(server_port, "/timeout"))

        # Update the timer to 1s to test connection timeout
        client.setTimeout(1)

        with pytest.raises(ResponseFailed) as exc_info:
            yield make_request_dfd(client, request)

        for err in exc_info.value.reasons:
            from scrapy.core.http2.protocol import H2ClientProtocol  # noqa: PLC0415

            if isinstance(err, TxTimeoutError):
                assert (
                    f"Connection was IDLE for more than {H2ClientProtocol.IDLE_TIMEOUT}s"
                    in str(err)
                )
                break
        else:
            pytest.fail("No TimeoutError raised.")

    @deferred_f_from_coro_f
    async def test_request_headers_received(
        self, server_port: int, client: H2ClientProtocol
    ) -> None:
        request = Request(
            self.get_url(server_port, "/request-headers"),
            headers={"header-1": "header value 1", "header-2": "header value 2"},
        )
        response = await make_request(client, request)
        assert response.status == 200
        assert response.request == request

        response_headers = json.loads(str(response.body, "utf-8"))
        assert isinstance(response_headers, dict)
        for k, v in request.headers.items():
            k_decoded, v_decoded = str(k, "utf-8"), str(v[0], "utf-8")
            assert k_decoded in response_headers
            assert v_decoded == response_headers[k_decoded]
