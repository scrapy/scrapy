import socket
from unittest.mock import Mock, patch

import pytest
from twisted.python.failure import Failure
from twisted.web._newclient import ResponseFailed

from scrapy import Request
from scrapy.downloadermiddlewares.error_headers import LenientHttpDownloaderMiddleware
from scrapy.http import Headers


@pytest.fixture
def fresh_middleware():
    return LenientHttpDownloaderMiddleware()


class TestErrorHeadersMiddleware:
    def test_error_header(self, fresh_middleware):
        # mock the exception that Twisted would raise on bad headers
        raw_exception = ValueError("not enough values to unpack (expected 2, got 1)")
        exception = ResponseFailed([Failure(raw_exception)])

        raw_response = (
            b"HTTP/1.0 200 OK\n"
            b"Bad header\n"  # <-- no ':' will raise ValueError
            b"\n"  # <-- no proper header/body separator
            b"Hello World"
        )

        # Simulate TCP streaming: return in 2+ chunks
        fake_socket = Mock(spec=socket.socket)

        fake_socket.recv.side_effect = [
            raw_response,  # first recv() - full malformed response
            b"",  # second recv() - EOF (connection closed)
        ]

        with patch("scrapy.downloadermiddlewares.error_headers.socket") as mock_socket:
            mock_socket.create_connection.return_value = fake_socket

            req = Request("http://example.com:80/path?q=123")
            response = fresh_middleware.process_exception(req, exception)

        assert response.status == 200
        assert response.headers == Headers({})
        assert response.body == b"Hello World"
        assert "BAD_HEADER_FALLBACK" in response.flags

        mock_socket.create_connection.assert_called_once()
        fake_socket.sendall.assert_called_once()
        assert fake_socket.recv.call_count == 2

    def test_valid_header(self, fresh_middleware):
        # Success path: no exception -> middleware should not interfere
        req = Request("http://example.com:80/path?q=123")

        with patch("scrapy.downloadermiddlewares.error_headers.socket") as mock_socket:
            response = fresh_middleware.process_exception(req, None)
            mock_socket.create_connection.assert_not_called()

        assert response is None
