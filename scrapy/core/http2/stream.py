import logging
from enum import Enum
from io import BytesIO
from typing import Callable, List
from urllib.parse import urlparse

from h2.connection import H2Connection
from h2.errors import ErrorCodes
from h2.exceptions import StreamClosedError
from twisted.internet.defer import Deferred, CancelledError
from twisted.internet.error import ConnectionClosed
from twisted.python.failure import Failure
from twisted.web.client import ResponseFailed

from scrapy.core.http2.types import H2ConnectionMetadataDict, H2ResponseDict
from scrapy.http import Request
from scrapy.http.headers import Headers
from scrapy.responsetypes import responsetypes

logger = logging.getLogger(__name__)


class InactiveStreamClosed(ConnectionClosed):
    """Connection was closed without sending request headers
    of the stream. This happens when a stream is waiting for other
    streams to close and connection is lost."""

    def __init__(self, request: Request):
        self.request = request


class InvalidHostname(Exception):

    def __init__(self, request: Request, expected_hostname, expected_netloc):
        self.request = request
        self.expected_hostname = expected_hostname
        self.expected_netloc = expected_netloc

    def __str__(self):
        return f'InvalidHostname: Expected {self.expected_hostname} or {self.expected_netloc} in {self.request}'


class StreamCloseReason(Enum):
    # Received a StreamEnded event
    ENDED = 1

    # Received a StreamReset event -- ended abruptly
    RESET = 2

    # Transport connection was lost
    CONNECTION_LOST = 3

    # Expected response body size is more than allowed limit
    MAXSIZE_EXCEEDED = 4

    # Response deferred is cancelled by the client
    # (happens when client called response_deferred.cancel())
    CANCELLED = 5

    # Connection lost and the stream was not initiated
    INACTIVE = 6

    # The hostname of the request is not same as of connected peer hostname
    # As a result sending this request will the end the connection
    INVALID_HOSTNAME = 7


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
        conn_metadata: H2ConnectionMetadataDict,
        cb_close: Callable[[int], None],
        download_maxsize: int = 0,
        download_warnsize: int = 0,
        fail_on_data_loss: bool = True
    ):
        """
        Arguments:
            stream_id -- For one HTTP/2 connection each stream is
                uniquely identified by a single integer
            request -- HTTP request
            connection -- HTTP/2 connection this stream belongs to.
            conn_metadata -- Reference to dictionary having metadata of HTTP/2 connection
            cb_close -- Method called when this stream is closed
                to notify the TCP connection instance.
        """
        self.stream_id = stream_id
        self._request = request
        self._conn = connection
        self._conn_metadata = conn_metadata
        self._cb_close = cb_close

        self._download_maxsize = self._request.meta.get('download_maxsize', download_maxsize)
        self._download_warnsize = self._request.meta.get('download_warnsize', download_warnsize)
        self._fail_on_dataloss = self._request.meta.get('download_fail_on_dataloss', fail_on_data_loss)

        self.request_start_time = None

        self.content_length = 0 if self._request.body is None else len(self._request.body)

        # Flag to keep track whether this stream has initiated the request
        self.request_sent = False

        # Flag to track whether we have logged about exceeding download warnsize
        self._reached_warnsize = False

        # Each time we send a data frame, we will decrease value by the amount send.
        self.remaining_content_length = self.content_length

        # Flag to keep track whether we have closed this stream
        self.stream_closed_local = False

        # Flag to keep track whether the server has closed the stream
        self.stream_closed_server = False

        # Private variable used to build the response
        # this response is then converted to appropriate Response class
        # passed to the response deferred callback
        self._response: H2ResponseDict = {
            'body': BytesIO(),
            'flow_controlled_size': 0,
            'headers': Headers({})
        }

        def _cancel(_):
            # Close this stream as gracefully as possible
            # Check if the stream has started
            if self.request_sent:
                self.reset_stream(StreamCloseReason.CANCELLED)
            else:
                self.close(StreamCloseReason.CANCELLED)

        self._deferred_response = Deferred(_cancel)

    def __str__(self):
        return f'Stream(id={self.stream_id!r})'

    __repr__ = __str__

    @property
    def _log_warnsize(self) -> bool:
        """Checks if we have received data which exceeds the download warnsize
        and whether we have not already logged about it.

        Returns:
            True if both the above conditions hold true
            False if any of the conditions is false
        """
        content_length_header = int(self._response['headers'].get(b'Content-Length', -1))
        return (
            self._download_warnsize
            and (
                self._response['flow_controlled_size'] > self._download_warnsize
                or content_length_header > self._download_warnsize
            )
            and not self._reached_warnsize
        )

    def get_response(self):
        """Simply return a Deferred which fires when response
        from the asynchronous request is available

        Returns:
            Deferred -- Calls the callback passing the response
        """
        return self._deferred_response

    def check_request_url(self) -> bool:
        # Make sure that we are sending the request to the correct URL
        url = urlparse(self._request.url)
        return (
            url.netloc == self._conn_metadata['hostname']
            or url.netloc == f'{self._conn_metadata["hostname"]}:{self._conn_metadata["port"]}'
            or url.netloc == f'{self._conn_metadata["ip_address"]}:{self._conn_metadata["port"]}'
        )

    def _get_request_headers(self):
        url = urlparse(self._request.url)

        path = url.path
        if url.query:
            path += '?' + url.query

        # Make sure pseudo-headers comes before all the other headers
        headers = [
            (':method', self._request.method),
            (':authority', url.netloc),
            (':scheme', 'https'),
            (':path', path),
        ]

        for name, value in self._request.headers.items():
            headers.append((name, value[0]))

        return headers

    def initiate_request(self):
        if self.check_request_url():
            headers = self._get_request_headers()
            self._conn.send_headers(self.stream_id, headers, end_stream=False)
            self.request_sent = True
            self.send_data()
        else:
            # Close this stream calling the response errback
            # Note that we have not sent any headers
            self.close(StreamCloseReason.INVALID_HOSTNAME)

    def send_data(self):
        """Called immediately after the headers are sent. Here we send all the
         data as part of the request.

         If the content length is 0 initially then we end the stream immediately and
         wait for response data.

         Warning: Only call this method when stream not closed from client side
            and has initiated request already by sending HEADER frame. If not then
            stream will raise ProtocolError (raise by h2 state machine).
         """
        if self.stream_closed_local:
            raise StreamClosedError(self.stream_id)

        # Firstly, check what the flow control window is for current stream.
        window_size = self._conn.local_flow_control_window(stream_id=self.stream_id)

        # Next, check what the maximum frame size is.
        max_frame_size = self._conn.max_outbound_frame_size

        # We will send no more than the window size or the remaining file size
        # of data in this call, whichever is smaller.
        bytes_to_send_size = min(window_size, self.remaining_content_length)

        # We now need to send a number of data frames.
        while bytes_to_send_size > 0:
            chunk_size = min(bytes_to_send_size, max_frame_size)

            data_chunk_start_id = self.content_length - self.remaining_content_length
            data_chunk = self._request.body[data_chunk_start_id:data_chunk_start_id + chunk_size]

            self._conn.send_data(self.stream_id, data_chunk, end_stream=False)

            bytes_to_send_size = bytes_to_send_size - chunk_size
            self.remaining_content_length = self.remaining_content_length - chunk_size

        self.remaining_content_length = max(0, self.remaining_content_length)

        # End the stream if no more data needs to be send
        if self.remaining_content_length == 0:
            self._conn.end_stream(self.stream_id)

        # Q. What about the rest of the data?
        # Ans: Remaining Data frames will be sent when we get a WindowUpdate frame

    def receive_window_update(self):
        """Flow control window size was changed.
        Send data that earlier could not be sent as we were
        blocked behind the flow control.
        """
        if self.remaining_content_length and not self.stream_closed_server and self.request_sent:
            self.send_data()

    def receive_data(self, data: bytes, flow_controlled_length: int):
        self._response['body'].write(data)
        self._response['flow_controlled_size'] += flow_controlled_length

        # We check maxsize here in case the Content-Length header was not received
        if self._download_maxsize and self._response['flow_controlled_size'] > self._download_maxsize:
            self.reset_stream(StreamCloseReason.MAXSIZE_EXCEEDED)
            return

        if self._log_warnsize:
            self._reached_warnsize = True
            warning_msg = (
                f'Received more ({self._response["flow_controlled_size"]}) bytes than download '
                f'warn size ({self._download_warnsize}) in request {self._request}'
            )
            logger.warning(warning_msg)

        # Acknowledge the data received
        self._conn.acknowledge_received_data(
            self._response['flow_controlled_size'],
            self.stream_id
        )

    def receive_headers(self, headers):
        for name, value in headers:
            self._response['headers'][name] = value

        # Check if we exceed the allowed max data size which can be received
        expected_size = int(self._response['headers'].get(b'Content-Length', -1))
        if self._download_maxsize and expected_size > self._download_maxsize:
            self.reset_stream(StreamCloseReason.MAXSIZE_EXCEEDED)
            return

        if self._log_warnsize:
            self._reached_warnsize = True
            warning_msg = (
                f'Expected response size ({expected_size}) larger than '
                f'download warn size ({self._download_warnsize}) in request {self._request}'
            )
            logger.warning(warning_msg)

    def reset_stream(self, reason=StreamCloseReason.RESET):
        """Close this stream by sending a RST_FRAME to the remote peer"""
        if self.stream_closed_local:
            raise StreamClosedError(self.stream_id)

        # Clear buffer earlier to avoid keeping data in memory for a long time
        self._response['body'].truncate(0)

        self.stream_closed_local = True
        self._conn.reset_stream(self.stream_id, ErrorCodes.REFUSED_STREAM)
        self.close(reason)

    def _is_data_lost(self) -> bool:
        assert self.stream_closed_server

        expected_size = self._response['flow_controlled_size']
        received_body_size = int(self._response['headers'][b'Content-Length'])

        return expected_size != received_body_size

    def close(self, reason: StreamCloseReason, error: Exception = None):
        """Based on the reason sent we will handle each case.

        Arguments:
            reason -- One if StreamCloseReason
        """
        if self.stream_closed_server:
            raise StreamClosedError(self.stream_id)

        if not isinstance(reason, StreamCloseReason):
            raise TypeError(f'Expected StreamCloseReason, received {reason.__class__.__qualname__}')

        self._cb_close(self.stream_id)
        self.stream_closed_server = True

        flags = None
        if b'Content-Length' not in self._response['headers']:
            # Missing Content-Length - {twisted.web.http.PotentialDataLoss}
            flags = ['partial']

        # NOTE: Order of handling the events is important here
        # As we immediately cancel the request when maxsize is exceeded while
        # receiving DATA_FRAME's when we have received the headers (not
        # having Content-Length)
        if reason is StreamCloseReason.MAXSIZE_EXCEEDED:
            expected_size = int(self._response['headers'].get(b'Content-Length', -1))
            error_msg = (
                f'Cancelling download of {self._request.url}: expected response '
                f'size ({expected_size}) larger than download max size ({self._download_maxsize}).'
            )
            logger.error(error_msg)
            self._deferred_response.errback(CancelledError(error_msg))

        elif reason is StreamCloseReason.ENDED:
            self._fire_response_deferred(flags)

        # Stream was abruptly ended here
        elif reason is StreamCloseReason.CANCELLED:
            # Client has cancelled the request. Remove all the data
            # received and fire the response deferred with no flags set

            # NOTE: The data is already flushed in Stream.reset_stream() called
            # immediately when the stream needs to be cancelled

            # There maybe no :status in headers, we make
            # HTTP Status Code: 499 - Client Closed Request
            self._response['headers'][':status'] = '499'
            self._fire_response_deferred()

        elif reason in (StreamCloseReason.RESET, StreamCloseReason.CONNECTION_LOST):
            self._deferred_response.errback(ResponseFailed([
                error if error else Failure()
            ]))

        elif reason is StreamCloseReason.INACTIVE:
            self._deferred_response.errback(InactiveStreamClosed(self._request))

        elif reason is StreamCloseReason.INVALID_HOSTNAME:
            self._deferred_response.errback(InvalidHostname(
                self._request,
                self._conn_metadata['hostname'],
                f'{self._conn_metadata["ip_address"]}:{self._conn_metadata["port"]}'
            ))

    def _fire_response_deferred(self, flags: List[str] = None):
        """Builds response from the self._response dict
        and fires the response deferred callback with the
        generated response instance"""

        body = self._response['body'].getvalue()
        response_cls = responsetypes.from_args(
            headers=self._response['headers'],
            url=self._request.url,
            body=body
        )

        response = response_cls(
            url=self._request.url,
            status=self._response['headers'][':status'],
            headers=self._response['headers'],
            body=body,
            request=self._request,
            flags=flags,
            certificate=self._conn_metadata['certificate'],
            ip_address=self._conn_metadata['ip_address']
        )

        self._deferred_response.callback(response)
