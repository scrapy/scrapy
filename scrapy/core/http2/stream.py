import logging
from typing import Dict
from urllib.parse import urlparse

from h2.connection import H2Connection
from h2.events import StreamEnded
from h2.exceptions import StreamClosedError
from twisted.internet.defer import Deferred

from scrapy.http import Request
from scrapy.http.headers import Headers
from scrapy.responsetypes import responsetypes

LOGGER = logging.getLogger(__name__)


class Stream:
    """Represents a single HTTP/2 Stream.

    Stream is a bidirectional flow of bytes within an established connection,
    which may carry one or more messages. Handles the transfer of HTTP Headers
    and Data frames.

    Role of this class is to
    1. Combine all the data frames
    """

    def __init__(
        self,
        stream_id: int,
        request: Request,
        connection: H2Connection,
        metadata: Dict,
        write_to_transport,
        cb_close
    ):
        """
        Arguments:
            stream_id {int} -- For one HTTP/2 connection each stream is
                uniquely identified by a single integer
            request {Request} -- HTTP request
            connection {H2Connection} -- HTTP/2 connection this stream belongs to.
            metadata {Dict} -- Reference to dictionary having metadata of HTTP/2 connection
            write_to_transport {callable} -- Method used to write & send data to the server
                This method should be used whenever some frame is to be sent to the server.
            cb_close {callable} -- Method called when this stream is closed
                to notify the TCP connection instance.
        """
        self.stream_id = stream_id
        self._request = request
        self._conn = connection
        self._metadata = metadata
        self._write_to_transport = write_to_transport
        self._cb_close = cb_close

        self._request_body = self._request.body
        self.content_length = 0 if self._request_body is None else len(self._request_body)

        # Flag to keep track whether this stream has initiated the request
        self.request_sent = False

        # Each time we send a data frame, we will decrease value by the amount send.
        self.remaining_content_length = self.content_length

        # Flag to keep track whether we have closed this stream
        self.stream_closed_local = False

        # Flag to keep track whether the server has closed the stream
        self.stream_closed_server = False

        # The amount of data received that counts against the flow control
        # window
        self._response_flow_controlled_size = 0

        # Private variable used to build the response
        # this response is then converted to appropriate Response class
        # passed to the response deferred callback
        self._response = {
            # Data received frame by frame from the server is appended
            # and passed to the response Deferred when completely received.
            'body': b'',

            # Headers received after sending the request
            'headers': Headers({})
        }

        # TODO: Add canceller for the Deferred below
        self._deferred_response = Deferred()

    def __str__(self):
        return "Stream(id={})".format(self.stream_id)

    __repr__ = __str__

    def get_response(self):
        """Simply return a Deferred which fires when response
        from the asynchronous request is available

        Returns:
            Deferred -- Calls the callback passing the response
        """
        return self._deferred_response

    def _get_request_headers(self):
        url = urlparse(self._request.url)

        # Make sure pseudo-headers comes before all the other headers
        headers = [
            (':method', self._request.method),
            (':authority', url.netloc),

            # TODO: Check if scheme can be 'http' for HTTP/2 ?
            (':scheme', 'https'),
            (':path', url.path),
        ]

        for name, value in self._request.headers.items():
            headers.append((name, value[0]))

        return headers

    def initiate_request(self):
        headers = self._get_request_headers()
        self._conn.send_headers(self.stream_id, headers, end_stream=False)
        self._write_to_transport()

        self.request_sent = True

        self.send_data()

    def send_data(self):
        """Called immediately after the headers are sent. Here we send all the
         data as part of the request.

         If the content length is 0 initially then we end the stream immediately and
         wait for response data.

         Warning: Only call this method when stream not closed from client side
            and has initiated request already by sending HEADER frame. If not then
            stream will be closed from client side with 499 response.

            TODO: Q. Should we instead raise ProtocolError here with a proper message?
         """
        if self.stream_closed_local or self.stream_closed_server:
            raise StreamClosedError(self.stream_id)
        elif not self.request_sent:
            self.close()
            return

        # TODO:
        #  1. Add test for sending very large data
        #  2. Add test for small data
        #  3. Both (1) and (2) should be tested for
        #    3.1 Large number of request
        #    3.2 Small number of requests

        # Firstly, check what the flow control window is for current stream.
        window_size = self._conn.local_flow_control_window(stream_id=self.stream_id)

        # Next, check what the maximum frame size is.
        max_frame_size = self._conn.max_outbound_frame_size

        # We will send no more than the window size or the remaining file size
        # of data in this call, whichever is smaller.
        bytes_to_send_size = min(window_size, self.remaining_content_length)

        # We now need to send a number of data frames.
        data_frames_sent = 0
        while bytes_to_send_size > 0:
            chunk_size = min(bytes_to_send_size, max_frame_size)

            data_chunk_start_id = self.content_length - self.remaining_content_length
            data_chunk = self._request_body[data_chunk_start_id:data_chunk_start_id + chunk_size]

            self._conn.send_data(self.stream_id, data_chunk, end_stream=False)

            data_frames_sent += 1
            bytes_to_send_size = bytes_to_send_size - chunk_size
            self.remaining_content_length = self.remaining_content_length - chunk_size

        self.remaining_content_length = max(0, self.remaining_content_length)
        LOGGER.debug("{} sending {}/{} data bytes ({} frames) to {}".format(
            self,
            self.content_length - self.remaining_content_length, self.content_length,
            data_frames_sent,
            self._metadata['ip_address'])
        )

        # End the stream if no more data needs to be send
        if self.remaining_content_length == 0:
            self.stream_closed_local = True
            self._conn.end_stream(self.stream_id)

        # Write data to transport -- Empty the outstanding data
        self._write_to_transport()

        # Q. What about the rest of the data?
        # Ans: Remaining Data frames will be sent when we get a WindowUpdate frame

    def receive_window_update(self, delta):
        """Flow control window size was changed.
        Send data that earlier could not be sent as we were
        blocked behind the flow control.

        Arguments:
            delta -- Window change delta
        """
        if self.remaining_content_length > 0 and not self.stream_closed_server:
            self.send_data()

    def receive_data(self, data: bytes, flow_controlled_length: int):
        self._response['body'] += data
        self._response_flow_controlled_size += flow_controlled_length

        # Acknowledge the data received
        self._conn.acknowledge_received_data(
            self._response_flow_controlled_size,
            self.stream_id
        )

    def receive_headers(self, headers):
        for name, value in headers:
            self._response['headers'][name] = value

    def close(self, event=None):
        """Based on the event sent we will handle each case.

        event: StreamEnded
        Stream is ended by the server hence no further
        data or headers should be expected on this stream.
        We will call the response deferred callback passing
        the response object

        event: StreamReset
        Stream reset via RST_FRAME by the upstream hence forcefully close
        this stream and send TODO: ?

        event: None
        No event is launched -- Hence we will simply close this stream
        """
        # TODO: In case of abruptly stream close
        #  Q1. Do we need to send the request again?
        #  Q2. What response should we send now?
        assert self.stream_closed_server is False
        self.stream_closed_server = True

        if not isinstance(event, StreamEnded):
            # TODO
            # Stream was abruptly ended here
            # Partial - Content-Length header not provided
            pass

        self._fire_response_deferred()
        self._cb_close(self.stream_id)

    def _fire_response_deferred(self, flags=None):
        """Builds response from the self._response dict
        and fires the response deferred callback with the
        generated response instance"""
        # TODO:
        #  1. Set flags, certificate, ip_address in response
        #  2. Should we fire this in case of
        #   2.1 StreamReset in between when data is received partially
        #   2.2 Forcefully closed the stream
        #  3. Update Client Side Status Codes here

        response_cls = responsetypes.from_args(
            headers=self._response['headers'],
            url=self._request.url,
            body=self._response['body']
        )

        # If there is :status in headers then
        # HTTP Status Code: 499 - Client Closed Request
        status = self._response['headers'].get(':status', '499')

        response = response_cls(
            url=self._request.url,
            status=status,
            headers=self._response['headers'],
            body=self._response['body'],
            request=self._request,
            flags=flags,
            certificate=self._metadata['certificate'],
            ip_address=self._metadata['ip_address']
        )

        self._deferred_response.callback(response)
