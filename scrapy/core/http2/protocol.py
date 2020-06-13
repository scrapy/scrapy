import logging
from typing import Dict, List

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    ConnectionTerminated, DataReceived, ResponseReceived, StreamEnded, StreamReset, WindowUpdated
)
from twisted.internet.protocol import connectionDone, Protocol

from scrapy.core.http2.stream import Stream
from scrapy.http import Request

LOGGER = logging.getLogger(__name__)


class H2ClientProtocol(Protocol):
    # TODO:
    #  1. Check for user-agent while testing
    #  2. Add support for cookies
    #  3. Handle priority updates

    def __init__(self):
        config = H2Configuration(client_side=True, header_encoding='utf-8')
        self.conn = H2Connection(config=config)

        # ID of the next request stream
        # Assuming each request stream creates a new response stream
        # we increment by 2 for each new request stream created
        self.next_stream_id = 1

        # Streams are stored in a dictionary keyed off their stream IDs
        self.streams: Dict[int, Stream] = {}

        # Boolean to keep track the connection is made
        # If requests are received before connection is made
        # we keep all requests in a pool and send them as the connection
        # is made
        self.is_connection_made = False
        self._pending_request_stream_pool: List[Stream] = []

    def _new_stream(self, request: Request):
        """Instantiates a new Stream object
        """
        stream = Stream(self.next_stream_id, request, self.conn)
        self.next_stream_id += 2

        self.streams[stream.stream_id] = stream
        return stream

    def _send_pending_requests(self):
        # TODO: handle MAX_CONCURRENT_STREAMS
        # Initiate all pending requests
        for stream in self._pending_request_stream_pool:
            stream.initiate_request()
            self._write_to_transport()

        self._pending_request_stream_pool.clear()

    def _write_to_transport(self):
        """ Write data to the underlying transport connection
        from the HTTP2 connection instance if any
        """
        data = self.conn.data_to_send()
        self.transport.write(data)

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
        self.conn.initiate_connection()
        self._write_to_transport()

        self._send_pending_requests()

        self.is_connection_made = True

    def dataReceived(self, data):
        events = self.conn.receive_data(data)
        self._handle_events(events)
        self._write_to_transport()

    def connectionLost(self, reason=connectionDone):
        """Called by Twisted when the transport connection is lost.
        """
        stream_ids = list(self.streams.keys())

        for stream in self._pending_request_stream_pool:
            stream_ids.remove(stream.stream_id)

        for stream_id in stream_ids:
            # TODO: Close each Stream instance in a clean manner
            self.conn.end_stream(stream_id)

    def _handle_events(self, events):
        """Private method which acts as a bridge between the events
        received from the HTTP/2 data and IH2EventsHandler

        Arguments:
            events {list} -- A list of events that the remote peer
                triggered by sending data
        """
        for event in events:
            LOGGER.debug(event)
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
            else:
                LOGGER.info("Received unhandled event {}".format(event))

    # Event handler functions starts here
    def connection_terminated(self, event: ConnectionTerminated):
        pass

    def data_received(self, event: DataReceived):
        stream_id = event.stream_id
        self.streams[stream_id].receive_data(event.data)

    def response_received(self, event: ResponseReceived):
        stream_id = event.stream_id
        self.streams[stream_id].receive_headers(event.headers)

    def stream_ended(self, event: StreamEnded):
        stream_id = event.stream_id
        self.streams[stream_id].end_stream()

    def stream_reset(self, event: StreamReset):
        pass

    def window_updated(self, event: WindowUpdated):
        stream_id = event.stream_id
        if stream_id != 0:
            self.streams[stream_id].window_updated()
