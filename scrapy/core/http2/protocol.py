import ipaddress
import itertools
import logging
from collections import deque
from ipaddress import IPv4Address, IPv6Address
from typing import Dict, List, Optional, Union

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.errors import ErrorCodes
from h2.events import (
    Event, ConnectionTerminated, DataReceived, ResponseReceived,
    SettingsAcknowledged, StreamEnded, StreamReset, UnknownFrameReceived,
    WindowUpdated
)
from h2.exceptions import FrameTooLargeError, H2Error
from twisted.internet.defer import Deferred
from twisted.internet.error import TimeoutError
from twisted.internet.interfaces import IHandshakeListener, IProtocolNegotiationFactory
from twisted.internet.protocol import connectionDone, Factory, Protocol
from twisted.internet.ssl import Certificate
from twisted.protocols.policies import TimeoutMixin
from twisted.python.failure import Failure
from twisted.web.client import URI
from zope.interface import implementer

from scrapy.core.http2.stream import Stream, StreamCloseReason
from scrapy.http import Request
from scrapy.settings import Settings
from scrapy.spiders import Spider


logger = logging.getLogger(__name__)


PROTOCOL_NAME = b"h2"


class InvalidNegotiatedProtocol(H2Error):

    def __init__(self, negotiated_protocol: bytes) -> None:
        self.negotiated_protocol = negotiated_protocol

    def __str__(self) -> str:
        return (f"Expected {PROTOCOL_NAME!r}, received {self.negotiated_protocol!r}")


class RemoteTerminatedConnection(H2Error):
    def __init__(
        self,
        remote_ip_address: Optional[Union[IPv4Address, IPv6Address]],
        event: ConnectionTerminated,
    ) -> None:
        self.remote_ip_address = remote_ip_address
        self.terminate_event = event

    def __str__(self) -> str:
        return f'Received GOAWAY frame from {self.remote_ip_address!r}'


class MethodNotAllowed405(H2Error):
    def __init__(self, remote_ip_address: Optional[Union[IPv4Address, IPv6Address]]) -> None:
        self.remote_ip_address = remote_ip_address

    def __str__(self) -> str:
        return f"Received 'HTTP/2.0 405 Method Not Allowed' from {self.remote_ip_address!r}"


@implementer(IHandshakeListener)
class H2ClientProtocol(Protocol, TimeoutMixin):
    IDLE_TIMEOUT = 240

    def __init__(self, uri: URI, settings: Settings, conn_lost_deferred: Deferred) -> None:
        """
        Arguments:
            uri -- URI of the base url to which HTTP/2 Connection will be made.
                uri is used to verify that incoming client requests have correct
                base URL.
            settings -- Scrapy project settings
            conn_lost_deferred -- Deferred fires with the reason: Failure to notify
                that connection was lost
        """
        self._conn_lost_deferred = conn_lost_deferred

        config = H2Configuration(client_side=True, header_encoding='utf-8')
        self.conn = H2Connection(config=config)

        # ID of the next request stream
        # Following the convention - 'Streams initiated by a client MUST
        # use odd-numbered stream identifiers' (RFC 7540 - Section 5.1.1)
        self._stream_id_generator = itertools.count(start=1, step=2)

        # Streams are stored in a dictionary keyed off their stream IDs
        self.streams: Dict[int, Stream] = {}

        # If requests are received before connection is made we keep
        # all requests in a pool and send them as the connection is made
        self._pending_request_stream_pool: deque = deque()

        # Save an instance of errors raised which lead to losing the connection
        # We pass these instances to the streams ResponseFailed() failure
        self._conn_lost_errors: List[BaseException] = []

        # Some meta data of this connection
        # initialized when connection is successfully made
        self.metadata: Dict = {
            # Peer certificate instance
            'certificate': None,

            # Address of the server we are connected to which
            # is updated when HTTP/2 connection is  made successfully
            'ip_address': None,

            # URI of the peer HTTP/2 connection is made
            'uri': uri,

            # Both ip_address and uri are used by the Stream before
            # initiating the request to verify that the base address

            # Variables taken from Project Settings
            'default_download_maxsize': settings.getint('DOWNLOAD_MAXSIZE'),
            'default_download_warnsize': settings.getint('DOWNLOAD_WARNSIZE'),

            # Counter to keep track of opened streams. This counter
            # is used to make sure that not more than MAX_CONCURRENT_STREAMS
            # streams are opened which leads to ProtocolError
            # We use simple FIFO policy to handle pending requests
            'active_streams': 0,

            # Flag to keep track if settings were acknowledged by the remote
            # This ensures that we have established a HTTP/2 connection
            'settings_acknowledged': False,
        }

    @property
    def h2_connected(self) -> bool:
        """Boolean to keep track of the connection status.
        This is used while initiating pending streams to make sure
        that we initiate stream only during active HTTP/2 Connection
        """
        return bool(self.transport.connected) and self.metadata['settings_acknowledged']

    @property
    def allowed_max_concurrent_streams(self) -> int:
        """We keep total two streams for client (sending data) and
        server side (receiving data) for a single request. To be safe
        we choose the minimum. Since this value can change in event
        RemoteSettingsChanged we make variable a property.
        """
        return min(
            self.conn.local_settings.max_concurrent_streams,
            self.conn.remote_settings.max_concurrent_streams
        )

    def _send_pending_requests(self) -> None:
        """Initiate all pending requests from the deque following FIFO
        We make sure that at any time {allowed_max_concurrent_streams}
        streams are active.
        """
        while (
            self._pending_request_stream_pool
            and self.metadata['active_streams'] < self.allowed_max_concurrent_streams
            and self.h2_connected
        ):
            self.metadata['active_streams'] += 1
            stream = self._pending_request_stream_pool.popleft()
            stream.initiate_request()
            self._write_to_transport()

    def pop_stream(self, stream_id: int) -> Stream:
        """Perform cleanup when a stream is closed
        """
        stream = self.streams.pop(stream_id)
        self.metadata['active_streams'] -= 1
        self._send_pending_requests()
        return stream

    def _new_stream(self, request: Request, spider: Spider) -> Stream:
        """Instantiates a new Stream object
        """
        stream = Stream(
            stream_id=next(self._stream_id_generator),
            request=request,
            protocol=self,
            download_maxsize=getattr(spider, 'download_maxsize', self.metadata['default_download_maxsize']),
            download_warnsize=getattr(spider, 'download_warnsize', self.metadata['default_download_warnsize']),
        )
        self.streams[stream.stream_id] = stream
        return stream

    def _write_to_transport(self) -> None:
        """ Write data to the underlying transport connection
        from the HTTP2 connection instance if any
        """
        # Reset the idle timeout as connection is still actively sending data
        self.resetTimeout()

        data = self.conn.data_to_send()
        self.transport.write(data)

    def request(self, request: Request, spider: Spider) -> Deferred:
        if not isinstance(request, Request):
            raise TypeError(f'Expected scrapy.http.Request, received {request.__class__.__qualname__}')

        stream = self._new_stream(request, spider)
        d = stream.get_response()

        # Add the stream to the request pool
        self._pending_request_stream_pool.append(stream)

        # If we receive a request when connection is idle
        # We need to initiate pending requests
        self._send_pending_requests()
        return d

    def connectionMade(self) -> None:
        """Called by Twisted when the connection is established. We can start
        sending some data now: we should open with the connection preamble.
        """
        # Initialize the timeout
        self.setTimeout(self.IDLE_TIMEOUT)

        destination = self.transport.getPeer()
        self.metadata['ip_address'] = ipaddress.ip_address(destination.host)

        # Initiate H2 Connection
        self.conn.initiate_connection()
        self._write_to_transport()

    def _lose_connection_with_error(self, errors: List[BaseException]) -> None:
        """Helper function to lose the connection with the error sent as a
        reason"""
        self._conn_lost_errors += errors
        self.transport.loseConnection()

    def handshakeCompleted(self) -> None:
        """
        Close the connection if it's not made via the expected protocol
        """
        if self.transport.negotiatedProtocol is not None and self.transport.negotiatedProtocol != PROTOCOL_NAME:
            # we have not initiated the connection yet, no need to send a GOAWAY frame to the remote peer
            self._lose_connection_with_error([InvalidNegotiatedProtocol(self.transport.negotiatedProtocol)])

    def _check_received_data(self, data: bytes) -> None:
        """Checks for edge cases where the connection to remote fails
        without raising an appropriate H2Error

        Arguments:
            data -- Data received from the remote
        """
        if data.startswith(b'HTTP/2.0 405 Method Not Allowed'):
            raise MethodNotAllowed405(self.metadata['ip_address'])

    def dataReceived(self, data: bytes) -> None:
        # Reset the idle timeout as connection is still actively receiving data
        self.resetTimeout()

        try:
            self._check_received_data(data)
            events = self.conn.receive_data(data)
            self._handle_events(events)
        except H2Error as e:
            if isinstance(e, FrameTooLargeError):
                # hyper-h2 does not drop the connection in this scenario, we
                # need to abort the connection manually.
                self._conn_lost_errors += [e]
                self.transport.abortConnection()
                return

            # Save this error as ultimately the connection will be dropped
            # internally by hyper-h2. Saved error will be passed to all the streams
            # closed with the connection.
            self._lose_connection_with_error([e])
        finally:
            self._write_to_transport()

    def timeoutConnection(self) -> None:
        """Called when the connection times out.
        We lose the connection with TimeoutError"""

        # Check whether there are open streams. If there are, we're going to
        # want to use the error code PROTOCOL_ERROR. If there aren't, use
        # NO_ERROR.
        if (
            self.conn.open_outbound_streams > 0
            or self.conn.open_inbound_streams > 0
            or self.metadata['active_streams'] > 0
        ):
            error_code = ErrorCodes.PROTOCOL_ERROR
        else:
            error_code = ErrorCodes.NO_ERROR
        self.conn.close_connection(error_code=error_code)
        self._write_to_transport()

        self._lose_connection_with_error([
            TimeoutError(f"Connection was IDLE for more than {self.IDLE_TIMEOUT}s")
        ])

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        """Called by Twisted when the transport connection is lost.
        No need to write anything to transport here.
        """
        # Cancel the timeout if not done yet
        self.setTimeout(None)

        # Notify the connection pool instance such that no new requests are
        # sent over current connection
        if not reason.check(connectionDone):
            self._conn_lost_errors.append(reason)

        self._conn_lost_deferred.callback(self._conn_lost_errors)

        for stream in self.streams.values():
            if stream.metadata['request_sent']:
                close_reason = StreamCloseReason.CONNECTION_LOST
            else:
                close_reason = StreamCloseReason.INACTIVE
            stream.close(close_reason, self._conn_lost_errors, from_protocol=True)

        self.metadata['active_streams'] -= len(self.streams)
        self.streams.clear()
        self._pending_request_stream_pool.clear()
        self.conn.close_connection()

    def _handle_events(self, events: List[Event]) -> None:
        """Private method which acts as a bridge between the events
        received from the HTTP/2 data and IH2EventsHandler

        Arguments:
            events -- A list of events that the remote peer triggered by sending data
        """
        for event in events:
            if isinstance(event, ConnectionTerminated):
                self.connection_terminated(event)
            elif isinstance(event, DataReceived):
                self.data_received(event)
            elif isinstance(event, ResponseReceived):
                self.response_received(event)
            elif isinstance(event, StreamEnded):
                self.stream_ended(event)
            elif isinstance(event, StreamReset):
                self.stream_reset(event)
            elif isinstance(event, WindowUpdated):
                self.window_updated(event)
            elif isinstance(event, SettingsAcknowledged):
                self.settings_acknowledged(event)
            elif isinstance(event, UnknownFrameReceived):
                logger.warning('Unknown frame received: %s', event.frame)

    # Event handler functions starts here
    def connection_terminated(self, event: ConnectionTerminated) -> None:
        self._lose_connection_with_error([
            RemoteTerminatedConnection(self.metadata['ip_address'], event)
        ])

    def data_received(self, event: DataReceived) -> None:
        try:
            stream = self.streams[event.stream_id]
        except KeyError:
            pass  # We ignore server-initiated events
        else:
            stream.receive_data(event.data, event.flow_controlled_length)

    def response_received(self, event: ResponseReceived) -> None:
        try:
            stream = self.streams[event.stream_id]
        except KeyError:
            pass  # We ignore server-initiated events
        else:
            stream.receive_headers(event.headers)

    def settings_acknowledged(self, event: SettingsAcknowledged) -> None:
        self.metadata['settings_acknowledged'] = True

        # Send off all the pending requests as now we have
        # established a proper HTTP/2 connection
        self._send_pending_requests()

        # Update certificate when our HTTP/2 connection is established
        self.metadata['certificate'] = Certificate(self.transport.getPeerCertificate())

    def stream_ended(self, event: StreamEnded) -> None:
        try:
            stream = self.pop_stream(event.stream_id)
        except KeyError:
            pass  # We ignore server-initiated events
        else:
            stream.close(StreamCloseReason.ENDED, from_protocol=True)

    def stream_reset(self, event: StreamReset) -> None:
        try:
            stream = self.pop_stream(event.stream_id)
        except KeyError:
            pass  # We ignore server-initiated events
        else:
            stream.close(StreamCloseReason.RESET, from_protocol=True)

    def window_updated(self, event: WindowUpdated) -> None:
        if event.stream_id != 0:
            self.streams[event.stream_id].receive_window_update()
        else:
            # Send leftover data for all the streams
            for stream in self.streams.values():
                stream.receive_window_update()


@implementer(IProtocolNegotiationFactory)
class H2ClientFactory(Factory):
    def __init__(self, uri: URI, settings: Settings, conn_lost_deferred: Deferred) -> None:
        self.uri = uri
        self.settings = settings
        self.conn_lost_deferred = conn_lost_deferred

    def buildProtocol(self, addr) -> H2ClientProtocol:
        return H2ClientProtocol(self.uri, self.settings, self.conn_lost_deferred)

    def acceptableProtocols(self) -> List[bytes]:
        return [PROTOCOL_NAME]
