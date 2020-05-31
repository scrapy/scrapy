from h2.connection import H2Connection
from h2.config import H2Configuration
from h2.events import (
    ConnectionTerminated, DataReceived, ResponseReceived, StreamEnded,
    StreamReset, TrailersReceived, WindowUpdated
)

from scrapy.http import Request

from twisted.internet.defer import maybeDeferred
from twisted.internet.protocol import Protocol

from urllib.parse import urlparse

from zope.interface import implementer, Interface


class IH2EventsHandler(Interface):
    def connection_terminated(event: ConnectionTerminated):
        pass

    def data_received(event: DataReceived):
        pass

    def response_received(event: ResponseReceived):
        pass

    def stream_ended(event: StreamEnded):
        pass

    def stream_reset(event: StreamReset):
        pass

    def trailers_received(event: TrailersReceived):
        pass

    def window_updated(event: WindowUpdated):
        pass


@implementer(IH2EventsHandler)
class H2ClientProtocol(Protocol):
    def __init__(self):
        config = H2Configuration(client_side=True)
        self.conn = H2Connection(config=config)
        
        # List of ongoing stream id's
        self.streams = []

    def request(self, _request: Request):
        url = urlparse(_request.url)

        request_headers = [
            (':method', _request.method),
            (':authority', url.netloc),
            (':scheme', url.scheme),
            (':path', url.path),
        ]

        # TODO: Check for user-agent while testing
        request_headers += list(_request.headers.items())

        # TODO: Add support for cookies here






    def connectionMade(self):
        """Called by Twisted when the connection is established. We can start
        sending some data now: we should open with the connection preamble.
        """
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())

    def dataReceived(self, data):
        events = self.conn.receive_data(data)

        self._handle_events(events)

        _data = self.conn.data_to_send()
        if _data:
            self.transport.write(data)

    def connectionLost(self, reason):
        """Called by Twisted when the transport connection is lost.
        """  

        for stream_id in self.streams:
            self.conn.end_stream(stream_id)

    def _handle_events(self, events):
        """Private method which acts as a bridge between the events
        received from the HTTP/2 data and IH2EventsHandler

        Arguments:
            events {list} -- A list of events that the remote peer
                triggered by sending data
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
            elif isinstance(event, TrailersReceived):
                self.trailers_received(event)
            elif isinstance(event, WindowUpdated):
                self.window_updated(event)

    def connection_terminated(self, event):
        pass

    def data_received(self, event):
        pass

    def response_received(self, event):
        pass

    def stream_ended(self, event):
        pass

    def stream_reset(self, event):
        pass

    def trailers_received(self, event):
        pass

    def window_updated(self, event):
        pass
