import logging
from enum import Enum
from io import BytesIO
from urllib.parse import urlparse
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from h2.errors import ErrorCodes
from h2.exceptions import H2Error, ProtocolError, StreamClosedError
from hpack import HeaderTuple
from twisted.internet.defer import Deferred, CancelledError
from twisted.internet.error import ConnectionClosed
from twisted.python.failure import Failure
from twisted.web.client import ResponseFailed

from scrapy.http import Request
from scrapy.http.headers import Headers
from scrapy.responsetypes import responsetypes

if TYPE_CHECKING:
    from scrapy.core.http2.protocol import H2ClientProtocol


logger = logging.getLogger(__name__)


class InactiveStreamClosed(ConnectionClosed):
    """Connection was closed without sending request headers
    of the stream. This happens when a stream is waiting for other
    streams to close and connection is lost."""

    def __init__(self, request: Request) -> None:
        self.request = request

    def __str__(self) -> str:
        return f'InactiveStreamClosed: Connection was closed without sending the request {self.request!r}'


class InvalidHostname(H2Error):

    def __init__(self, request: Request, expected_hostname: str, expected_netloc: str) -> None:
        self.request = request
        self.expected_hostname = expected_hostname
        self.expected_netloc = expected_netloc

    def __str__(self) -> str:
        return f'InvalidHostname: Expected {self.expected_hostname} or {self.expected_netloc} in {self.request}'


class StreamCloseReason(Enum):
    # Received a StreamEnded event from the remote
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
        protocol: "H2ClientProtocol",
        download_maxsize: int = 0,
        download_warnsize: int = 0,
    ) -> None:
        """
        Arguments:
            stream_id -- Unique identifier for the stream within a single HTTP/2 connection
            request -- The HTTP request associated to the stream
            protocol -- Parent H2ClientProtocol instance
        """
        self.stream_id: int = stream_id
        self._request: Request = request
        self._protocol: "H2ClientProtocol" = protocol

        self._download_maxsize = self._request.meta.get('download_maxsize', download_maxsize)
        self._download_warnsize = self._request.meta.get('download_warnsize', download_warnsize)

        # Metadata of an HTTP/2 connection stream
        # initialized when stream is instantiated
        self.metadata: Dict = {
            'request_content_length': 0 if self._request.body is None else len(self._request.body),

            # Flag to keep track whether the stream has initiated the request
            'request_sent': False,

            # Flag to track whether we have logged about exceeding download warnsize
            'reached_warnsize': False,

            # Each time we send a data frame, we will decrease value by the amount send.
            'remaining_content_length': 0 if self._request.body is None else len(self._request.body),

            # Flag to keep track whether client (self) have closed this stream
            'stream_closed_local': False,

            # Flag to keep track whether the server has closed the stream
            'stream_closed_server': False,
        }

        # Private variable used to build the response
        # this response is then converted to appropriate Response class
        # passed to the response deferred callback
        self._response: Dict = {
            # Data received frame by frame from the server is appended
            # and passed to the response Deferred when completely received.
            'body': BytesIO(),

            # The amount of data received that counts against the
            # flow control window
            'flow_controlled_size': 0,

            # Headers received after sending the request
            'headers': Headers({}),
        }

        def _cancel(_) -> None:
            # Close this stream as gracefully as possible
            # If the associated request is initiated we reset this stream
            # else we directly call close() method
            if self.metadata['request_sent']:
                self.reset_stream(StreamCloseReason.CANCELLED)
            else:
                self.close(StreamCloseReason.CANCELLED)

        self._deferred_response = Deferred(_cancel)

    def __str__(self) -> str:
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
            and not self.metadata['reached_warnsize']
        )

    def get_response(self) -> Deferred:
        """Simply return a Deferred which fires when response
        from the asynchronous request is available
        """
        return self._deferred_response

    def check_request_url(self) -> bool:
        # Make sure that we are sending the request to the correct URL
        url = urlparse(self._request.url)
        return (
            url.netloc == str(self._protocol.metadata['uri'].host, 'utf-8')
            or url.netloc == str(self._protocol.metadata['uri'].netloc, 'utf-8')
            or url.netloc == f'{self._protocol.metadata["ip_address"]}:{self._protocol.metadata["uri"].port}'
        )

    def _get_request_headers(self) -> List[Tuple[str, str]]:
        url = urlparse(self._request.url)

        path = url.path
        if url.query:
            path += '?' + url.query

        # This pseudo-header field MUST NOT be empty for "http" or "https"
        # URIs; "http" or "https" URIs that do not contain a path component
        # MUST include a value of '/'. The exception to this rule is an
        # OPTIONS request for an "http" or "https" URI that does not include
        # a path component; these MUST include a ":path" pseudo-header field
        # with a value of '*' (refer RFC 7540 - Section 8.1.2.3)
        if not path:
            path = '*' if self._request.method == 'OPTIONS' else '/'

        # Make sure pseudo-headers comes before all the other headers
        headers = [
            (':method', self._request.method),
            (':authority', url.netloc),
        ]

        # The ":scheme" and ":path" pseudo-header fields MUST
        # be omitted for CONNECT method (refer RFC 7540 - Section 8.3)
        if self._request.method != 'CONNECT':
            headers += [
                (':scheme', self._protocol.metadata['uri'].scheme),
                (':path', path),
            ]

        content_length = str(len(self._request.body))
        headers.append(('Content-Length', content_length))

        content_length_name = self._request.headers.normkey(b'Content-Length')
        for name, values in self._request.headers.items():
            for value in values:
                value = str(value, 'utf-8')
                if name == content_length_name:
                    if value != content_length:
                        logger.warning(
                            'Ignoring bad Content-Length header %r of request %r, '
                            'sending %r instead',
                            value,
                            self._request,
                            content_length,
                        )
                    continue
                headers.append((str(name, 'utf-8'), value))

        return headers

    def initiate_request(self) -> None:
        if self.check_request_url():
            headers = self._get_request_headers()
            self._protocol.conn.send_headers(self.stream_id, headers, end_stream=False)
            self.metadata['request_sent'] = True
            self.send_data()
        else:
            # Close this stream calling the response errback
            # Note that we have not sent any headers
            self.close(StreamCloseReason.INVALID_HOSTNAME)

    def send_data(self) -> None:
        """Called immediately after the headers are sent. Here we send all the
         data as part of the request.

         If the content length is 0 initially then we end the stream immediately and
         wait for response data.

         Warning: Only call this method when stream not closed from client side
            and has initiated request already by sending HEADER frame. If not then
            stream will raise ProtocolError (raise by h2 state machine).
         """
        if self.metadata['stream_closed_local']:
            raise StreamClosedError(self.stream_id)

        # Firstly, check what the flow control window is for current stream.
        window_size = self._protocol.conn.local_flow_control_window(stream_id=self.stream_id)

        # Next, check what the maximum frame size is.
        max_frame_size = self._protocol.conn.max_outbound_frame_size

        # We will send no more than the window size or the remaining file size
        # of data in this call, whichever is smaller.
        bytes_to_send_size = min(window_size, self.metadata['remaining_content_length'])

        # We now need to send a number of data frames.
        while bytes_to_send_size > 0:
            chunk_size = min(bytes_to_send_size, max_frame_size)

            data_chunk_start_id = self.metadata['request_content_length'] - self.metadata['remaining_content_length']
            data_chunk = self._request.body[data_chunk_start_id:data_chunk_start_id + chunk_size]

            self._protocol.conn.send_data(self.stream_id, data_chunk, end_stream=False)

            bytes_to_send_size -= chunk_size
            self.metadata['remaining_content_length'] -= chunk_size

        self.metadata['remaining_content_length'] = max(0, self.metadata['remaining_content_length'])

        # End the stream if no more data needs to be send
        if self.metadata['remaining_content_length'] == 0:
            self._protocol.conn.end_stream(self.stream_id)

        # Q. What about the rest of the data?
        # Ans: Remaining Data frames will be sent when we get a WindowUpdate frame

    def receive_window_update(self) -> None:
        """Flow control window size was changed.
        Send data that earlier could not be sent as we were
        blocked behind the flow control.
        """
        if (
            self.metadata['remaining_content_length']
            and not self.metadata['stream_closed_server']
            and self.metadata['request_sent']
        ):
            self.send_data()

    def receive_data(self, data: bytes, flow_controlled_length: int) -> None:
        self._response['body'].write(data)
        self._response['flow_controlled_size'] += flow_controlled_length

        # We check maxsize here in case the Content-Length header was not received
        if self._download_maxsize and self._response['flow_controlled_size'] > self._download_maxsize:
            self.reset_stream(StreamCloseReason.MAXSIZE_EXCEEDED)
            return

        if self._log_warnsize:
            self.metadata['reached_warnsize'] = True
            warning_msg = (
                f'Received more ({self._response["flow_controlled_size"]}) bytes than download '
                f'warn size ({self._download_warnsize}) in request {self._request}'
            )
            logger.warning(warning_msg)

        # Acknowledge the data received
        self._protocol.conn.acknowledge_received_data(
            self._response['flow_controlled_size'],
            self.stream_id
        )

    def receive_headers(self, headers: List[HeaderTuple]) -> None:
        for name, value in headers:
            self._response['headers'][name] = value

        # Check if we exceed the allowed max data size which can be received
        expected_size = int(self._response['headers'].get(b'Content-Length', -1))
        if self._download_maxsize and expected_size > self._download_maxsize:
            self.reset_stream(StreamCloseReason.MAXSIZE_EXCEEDED)
            return

        if self._log_warnsize:
            self.metadata['reached_warnsize'] = True
            warning_msg = (
                f'Expected response size ({expected_size}) larger than '
                f'download warn size ({self._download_warnsize}) in request {self._request}'
            )
            logger.warning(warning_msg)

    def reset_stream(self, reason: StreamCloseReason = StreamCloseReason.RESET) -> None:
        """Close this stream by sending a RST_FRAME to the remote peer"""
        if self.metadata['stream_closed_local']:
            raise StreamClosedError(self.stream_id)

        # Clear buffer earlier to avoid keeping data in memory for a long time
        self._response['body'].truncate(0)

        self.metadata['stream_closed_local'] = True
        self._protocol.conn.reset_stream(self.stream_id, ErrorCodes.REFUSED_STREAM)
        self.close(reason)

    def close(
        self,
        reason: StreamCloseReason,
        errors: Optional[List[BaseException]] = None,
        from_protocol: bool = False,
    ) -> None:
        """Based on the reason sent we will handle each case.
        """
        if self.metadata['stream_closed_server']:
            raise StreamClosedError(self.stream_id)

        if not isinstance(reason, StreamCloseReason):
            raise TypeError(f'Expected StreamCloseReason, received {reason.__class__.__qualname__}')

        # Have default value of errors as an empty list as
        # some cases can add a list of exceptions
        errors = errors or []

        if not from_protocol:
            self._protocol.pop_stream(self.stream_id)

        self.metadata['stream_closed_server'] = True

        # We do not check for Content-Length or Transfer-Encoding in response headers
        # and add `partial` flag as in HTTP/1.1 as 'A request or response that includes
        # a payload body can include a content-length header field' (RFC 7540 - Section 8.1.2.6)

        # NOTE: Order of handling the events is important here
        # As we immediately cancel the request when maxsize is exceeded while
        # receiving DATA_FRAME's when we have received the headers (not
        # having Content-Length)
        if reason is StreamCloseReason.MAXSIZE_EXCEEDED:
            expected_size = int(self._response['headers'].get(
                b'Content-Length',
                self._response['flow_controlled_size'])
            )
            error_msg = (
                f'Cancelling download of {self._request.url}: received response '
                f'size ({expected_size}) larger than download max size ({self._download_maxsize})'
            )
            logger.error(error_msg)
            self._deferred_response.errback(CancelledError(error_msg))

        elif reason is StreamCloseReason.ENDED:
            self._fire_response_deferred()

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

        elif reason is StreamCloseReason.RESET:
            self._deferred_response.errback(ResponseFailed([
                Failure(
                    f'Remote peer {self._protocol.metadata["ip_address"]} sent RST_STREAM',
                    ProtocolError
                )
            ]))

        elif reason is StreamCloseReason.CONNECTION_LOST:
            self._deferred_response.errback(ResponseFailed(errors))

        elif reason is StreamCloseReason.INACTIVE:
            errors.insert(0, InactiveStreamClosed(self._request))
            self._deferred_response.errback(ResponseFailed(errors))

        else:
            assert reason is StreamCloseReason.INVALID_HOSTNAME
            self._deferred_response.errback(InvalidHostname(
                self._request,
                str(self._protocol.metadata['uri'].host, 'utf-8'),
                f'{self._protocol.metadata["ip_address"]}:{self._protocol.metadata["uri"].port}'
            ))

    def _fire_response_deferred(self) -> None:
        """Builds response from the self._response dict
        and fires the response deferred callback with the
        generated response instance"""

        body = self._response['body'].getvalue()
        response_cls = responsetypes.from_args(
            headers=self._response['headers'],
            url=self._request.url,
            body=body,
        )

        response = response_cls(
            url=self._request.url,
            status=int(self._response['headers'][':status']),
            headers=self._response['headers'],
            body=body,
            request=self._request,
            certificate=self._protocol.metadata['certificate'],
            ip_address=self._protocol.metadata['ip_address'],
            protocol='h2',
        )

        self._deferred_response.callback(response)
