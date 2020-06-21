import ipaddress
import itertools
import logging
from collections import deque

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    DataReceived, ResponseReceived, SettingsAcknowledged,
    StreamEnded, StreamReset, WindowUpdated
)
from twisted.internet.protocol import connectionDone, Protocol

from scrapy.core.http2.stream import Stream, StreamCloseReason
from scrapy.http import Request

LOGGER = logging.getLogger(__name__)


class H2ClientProtocol(Protocol):
    # TODO:
    #  1. Check for user-agent while testing
    #  2. Add support for cookies
    #  3. Handle priority updates (Not required)
    #  4. Handle case when received events have StreamID = 0 (applied to H2Connection)
    #  1 & 2:
    #   - Automatically handled by the Request middleware
    #   - request.headers will have 'Set-Cookie' value

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
        self.streams = {}

        # Boolean to keep track the connection is made
        # If requests are received before connection is made
        # we keep all requests in a pool and send them as the connection
        # is made
        self.is_connection_made = False
        self._pending_request_stream_pool = deque()

        # Some meta data of this connection
        # initialized when connection is successfully made
        self._metadata = {
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
            write_to_transport=self._write_to_transport,
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

        LOGGER.debug("Sent {} bytes to {} via transport".format(len(data), self._metadata['ip_address']))

    def request(self, _request: Request):
        stream = self._new_stream(_request)
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
        LOGGER.info('Connection made to {}'.format(self.destination))

        self._metadata['certificate'] = self.transport.getPeerCertificate()
        self._metadata['ip_address'] = ipaddress.ip_address(self.destination.host)

        self.conn.initiate_connection()
        self._write_to_transport()
        self.is_connection_made = True

    def dataReceived(self, data):
        events = self.conn.receive_data(data)
        self._handle_events(events)
        self._write_to_transport()

    def connectionLost(self, reason=connectionDone):
        """Called by Twisted when the transport connection is lost.
        No need to write anything to transport here.
        """
        # Pop all streams which were pending and were not yet started
        for stream_id in list(self.streams):
            self.streams[stream_id].close(StreamCloseReason.CONNECTION_LOST)

        self.conn.close_connection()

        LOGGER.info("Connection lost with reason " + str(reason))

    def _handle_events(self, events):
        """Private method which acts as a bridge between the events
        received from the HTTP/2 data and IH2EventsHandler

        Arguments:
            events {list} -- A list of events that the remote peer
                triggered by sending data
        """
        for event in events:
            LOGGER.debug(event)
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
                LOGGER.info("Received unhandled event {}".format(event))

    # Event handler functions starts here
    def data_received(self, event: DataReceived):
        stream_id = event.stream_id
        self.streams[stream_id].receive_data(event.data, event.flow_controlled_length)

    def response_received(self, event: ResponseReceived):
        stream_id = event.stream_id
        self.streams[stream_id].receive_headers(event.headers)

    def settings_acknowledged(self, event: SettingsAcknowledged):
        # Send off all the pending requests
        # as now we have established a proper HTTP/2 connection
        self._send_pending_requests()

    def stream_ended(self, event: StreamEnded):
        stream_id = event.stream_id
        self.streams[stream_id].close(StreamCloseReason.ENDED)

    def stream_reset(self, event: StreamReset):
        # TODO: event.stream_id was abruptly closed
        #  Q. What should be the response? (Failure/Partial/???)
        self.streams[event.stream_id].close(StreamCloseReason.RESET)

    def window_updated(self, event: WindowUpdated):
        stream_id = event.stream_id
        if stream_id != 0:
            self.streams[stream_id].receive_window_update()
        else:
            # Send leftover data for all the streams
            for stream in self.streams.values():
                stream.receive_window_update()
