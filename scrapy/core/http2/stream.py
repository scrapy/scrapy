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
            connection {H2Connection} -- HTTP/2 connection this stream belongs to.
        """
        self.stream_id = stream_id
        self._request = request
        self._client_protocol = connection

        self._request_body = self._request.body
        self.content_length = 0 if self._request_body is None else len(self._request_body)

        # Each time we send a data frame, we will decrease value by the amount send.
        self.remaining_content_length = self.content_length

        # Flag to keep track whether we have ended this stream
        self.stream_ended = True

        # Data received frame by frame from the server is appended
        # and passed to the response Deferred when completely received.
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
            (":path", url.path),
            # ("Content-Length", str(self.content_length))

            # TODO: Make sure 'Content-Type' and 'Content-Encoding' headers
            #  are sent for request having body
        ]

        self._client_protocol.send_headers(self.stream_id, http2_request_headers)
        self.send_data()

    def send_data(self):
        """Called immediately after the headers are sent. Here we send all the
         data as part of the request.

         If the content length is 0 initially then we end the stream immediately and
         wait for response data.
         """

        # TODO:
        #  1. Add test for sending very large data
        #  2. Add test for small data
        #  3. Both (1) and (2) should be tested for
        #    3.1 Large number of request
        #    3.2 Small number of requests

        # Firstly, check what the flow control window is for current stream.
        window_size = self._client_protocol.conn.local_flow_control_window(stream_id=self.stream_id)

        # Next, check what the maximum frame size is.
        max_frame_size = self._client_protocol.conn.max_outbound_frame_size

        # We will send no more than the window size or the remaining file size
        # of data in this call, whichever is smaller.
        bytes_to_send = min(window_size, self.remaining_content_length)

        # We now need to send a number of data frames.
        while bytes_to_send > 0:
            chunk_size = min(bytes_to_send, max_frame_size)

            data_chunk_start = self.content_length - self.remaining_content_length
            data_chunk = self._request_body[data_chunk_start:data_chunk_start + chunk_size]

            self._client_protocol.send_data(self.stream_id, data_chunk, end_stream=False)

            bytes_to_send = max(0, bytes_to_send - chunk_size)
            self.remaining_content_length = max(0, self.remaining_content_length - chunk_size)

        # End the stream if no more data has to be send
        if self.remaining_content_length == 0:
            self._client_protocol.end_stream(self.stream_id)
        else:
            # TODO: Continue from here :)
            pass

    def window_updated(self):
        """Flow control window size was changed.
        Send data that earlier could not be sent as we were
        blocked behind the flow control.
        """
        if self.remaining_content_length > 0 and not self.stream_ended:
            self.send_data()

    def receive_data(self, data: bytes):
        self._response_data += data

    def receive_headers(self, headers):
        for name, value in headers:
            self._response_headers[name] = value

    def end_stream(self):
        """Stream is ended by the server hence no further
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
