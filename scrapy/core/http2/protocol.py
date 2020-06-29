import ipaddress
import itertools
import logging
from collections import deque
from typing import Union, Dict

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    DataReceived, ResponseReceived, SettingsAcknowledged,
    StreamEnded, StreamReset, WindowUpdated
)
from h2.exceptions import ProtocolError
from twisted.internet.protocol import connectionDone, Protocol
from twisted.internet.ssl import Certificate

from scrapy.core.http2.stream import Stream, StreamCloseReason
from scrapy.core.http2.types import H2ConnectionMetadataDict
from scrapy.http import Request

logger = logging.getLogger(__name__)


class H2ClientProtocol(Protocol):
    def __init__(self):
        config = H2Configuration(client_side=True, header_encoding='utf-8')
        self.conn = H2Connection(config=config)

        # Address of the server we are connected to
        # these are updated when connection is successfully made
        self.destination = None

        # ID of the next request stream
        # Following the convention made by hyper-h2 each client ID
        # will be odd.
        self.stream_id_count = itertools.count(start=1, step=2)

        # Streams are stored in a dictionary keyed off their stream IDs
        self.streams: Dict[int, Stream] = {}

        # Boolean to keep track the connection is made
        # If requests are received before connection is made
        # we keep all requests in a pool and send them as the connection
        # is made
        self.is_connection_made = False
        self._pending_request_stream_pool = deque()

        # Save an instance of ProtocolError raised by hyper-h2
        # We pass this instance to the streams ResponseFailed() failure
        self._protocol_error: Union[None, ProtocolError] = None

        self._metadata: H2ConnectionMetadataDict = {
            'certificate': None,
            'ip_address': None
        }

    def _stream_close_cb(self, stream_id: int):
        """Called when stream is closed completely
        """
        self.streams.pop(stream_id, None)

    def _new_stream(self, request: Request):
        """Instantiates a new Stream object
        """
        stream_id = next(self.stream_id_count)

        stream = Stream(
            stream_id=stream_id,
            request=request,
            connection=self.conn,
            conn_metadata=self._metadata,
            cb_close=self._stream_close_cb
        )

        self.streams[stream.stream_id] = stream
        return stream

    def _send_pending_requests(self):
        # TODO: handle MAX_CONCURRENT_STREAMS
        # Initiate all pending requests
        while self._pending_request_stream_pool:
            stream = self._pending_request_stream_pool.popleft()
            stream.initiate_request()

    def _write_to_transport(self):
        """ Write data to the underlying transport connection
        from the HTTP2 connection instance if any
        """
        data = self.conn.data_to_send()
        self.transport.write(data)

        logger.debug("Sent {} bytes to {} via transport".format(len(data), self._metadata['ip_address']))

    def request(self, request: Request):
        stream = self._new_stream(request)
        d = stream.get_response()

        # If connection is not yet established then add the
        # stream to pool or initiate request
        if self.is_connection_made:
            stream.initiate_request()
        else:
            self._pending_request_stream_pool.append(stream)

        return d

    def connectionMade(self):
        """Called by Twisted when the connection is established. We can start
        sending some data now: we should open with the connection preamble.
        """
        self.destination = self.transport.getPeer()
        logger.info('Connection made to {}'.format(self.destination))

        self._metadata['certificate'] = Certificate(self.transport.getPeerCertificate())
        self._metadata['ip_address'] = ipaddress.ip_address(self.destination.host)

        self.conn.initiate_connection()
        self._write_to_transport()
        self.is_connection_made = True

    def dataReceived(self, data):
        try:
            events = self.conn.receive_data(data)
            self._handle_events(events)
        except ProtocolError as e:
            # TODO: In case of InvalidBodyLengthError -- terminate only one stream

            # Save this error as ultimately the connection will be dropped
            # internally by hyper-h2. Saved error will be passed to all the streams
            # closed with the connection.
            self._protocol_error = e

            # We lose the transport connection here
            self.transport.loseConnection()
        finally:
            self._write_to_transport()

    def connectionLost(self, reason=connectionDone):
        """Called by Twisted when the transport connection is lost.
        No need to write anything to transport here.
        """
        # Pop all streams which were pending and were not yet started
        # NOTE: Stream.close() pops the element from the streams dictionary
        # which raises `RuntimeError: dictionary changed size during iteration`
        # Hence, we copy the streams into a list.
        for stream in list(self.streams.values()):
            stream.close(StreamCloseReason.CONNECTION_LOST, self._protocol_error)

        self.conn.close_connection()

        if not reason.check(connectionDone):
            logger.warning("Connection lost with reason " + str(reason))

    def _handle_events(self, events):
        """Private method which acts as a bridge between the events
        received from the HTTP/2 data and IH2EventsHandler

        Arguments:
            events {list} -- A list of events that the remote peer
                triggered by sending data
        """
        for event in events:
            logger.debug(event)
            if isinstance(event, DataReceived):
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
            else:
                logger.info("Received unhandled event {}".format(event))

    # Event handler functions starts here
    def data_received(self, event: DataReceived):
        self.streams[event.stream_id].receive_data(event.data, event.flow_controlled_length)

    def response_received(self, event: ResponseReceived):
        self.streams[event.stream_id].receive_headers(event.headers)

    def settings_acknowledged(self, event: SettingsAcknowledged):
        # Send off all the pending requests
        # as now we have established a proper HTTP/2 connection
        self._send_pending_requests()

    def stream_ended(self, event: StreamEnded):
        self.streams[event.stream_id].close(StreamCloseReason.ENDED)

    def stream_reset(self, event: StreamReset):
        self.streams[event.stream_id].close(StreamCloseReason.RESET)

    def window_updated(self, event: WindowUpdated):
        stream_id = event.stream_id
        if stream_id != 0:
            self.streams[stream_id].receive_window_update()
        else:
            # Send leftover data for all the streams
            for stream in self.streams.values():
                stream.receive_window_update()
