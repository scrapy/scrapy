from urllib.parse import urlparse

from twisted.internet.defer import Deferred

from scrapy.http import Request, Response
from scrapy.http.headers import Headers


class Stream:
    """Represents a single HTTP/2 Stream.

    Stream is a bidirectional flow of bytes within an established connection,
    which may carry one or more messages. Handles the transfer of HTTP Headers
    and Data frames.

    Role of this class is to
    1. Combine all the data frames
    """

    def __init__(self, stream_id: int, request: Request, connection):
        """
        Arguments:
            stream_id {int} -- For one HTTP/2 connection each stream is
                uniquely identified by a single integer
            request {Request} -- HTTP request
            connection {H2ClientProtocol} -- HTTP/2 connection this stream belongs to
        """

        self.stream_id = stream_id
        self._request = request
        self._conn = connection

        self._response_data = b""

        # Headers received after sending the request
        self._response_headers = Headers({})

        # TODO: Add canceller for the Deferred below
        self._deferred_response = Deferred()

    def get_response(self):
        """Simply return a Deferred which fires when response
        from the asynchronous request is available

        Returns:
            Deferred -- Calls the callback passing the response
        """
        return self._deferred_response

    def initiate_request(self):
        http2_request_headers = []
        for name, value in self._request.headers.items():
            http2_request_headers.append((name, value))

        url = urlparse(self._request.url)
        http2_request_headers += [
            (":method", self._request.method),
            (":authority", url.netloc),

            # TODO: Check if scheme can be "http" for HTTP/2 ?
            (":scheme", "https"),
            (":path", url.path)
        ]

        self._conn.send_headers(self.stream_id, http2_request_headers)

    def receive_data(self, data: bytes):
        self._response_data += data

    def receive_headers(self, headers):
        for name, value in headers:
            self._response_headers[name] = value

    def end_stream(self):
        """Stream is ended by the resource hence no further
        data or headers should be expected on this stream.

        We will call the response deferred callback passing
        the response object
        """
        # TODO: Set flags, certificate, ip_address
        response = Response(
            url=self._request.url,
            status=self._response_headers[":status"],
            headers=self._response_headers,
            body=self._response_data,
            request=self._request
        )
        self._deferred_response.callback(response)
