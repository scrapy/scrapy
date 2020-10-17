from collections import deque
from typing import Deque, Dict, List, Optional, Tuple, Union
from urllib.parse import urldefrag

from twisted.internet.base import ReactorBase
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IHandshakeListener, IProtocolNegotiationFactory
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.protocol import connectionDone
from twisted.web._newclient import HTTP11ClientProtocol
from twisted.web.client import BrowserLikePolicyForHTTPS, _StandardEndpointFactory, URI
from zope.interface import implementer

from scrapy.core.downloader.contextfactory import AcceptableProtocolsContextFactory, load_context_factory_from_settings
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.core.downloader.handlers.http2 import H2DownloadHandler
from scrapy.core.http2.protocol import H2ClientProtocol
from scrapy.http.request import Request
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.datatypes import LocalCache
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.python import to_bytes, without_none_values


@implementer(IHandshakeListener)
class NegotiateProtocol(Protocol):
    def __init__(self, negotiated_protocol_deferred: Deferred):
        self._negotiated_protocol_deferred = negotiated_protocol_deferred

    def connectionLost(self, reason=connectionDone):
        if not self._negotiated_protocol_deferred.called:
            self._negotiated_protocol_deferred.errback(reason)

    def handshakeCompleted(self) -> None:
        self._negotiated_protocol_deferred.callback(self.transport)


@implementer(IProtocolNegotiationFactory)
class NegotiateProtocolFactory(Factory):
    def __init__(
            self,
            acceptable_protocols: List[bytes],
            negotiated_protocol_deferred: Deferred
    ) -> None:
        self.acceptable_protocols = acceptable_protocols
        self.negotiated_protocol_deferred = negotiated_protocol_deferred

    def buildProtocol(self, addr) -> NegotiateProtocol:
        return NegotiateProtocol(self.negotiated_protocol_deferred)

    def acceptableProtocols(self) -> List[bytes]:
        return self.acceptable_protocols


class NegotiateAgent:
    def __init__(
            self, reactor: ReactorBase,
            acceptable_protocols: List,
            context_factory=BrowserLikePolicyForHTTPS(),
            connect_timeout: Optional[float] = None, bind_address: Optional[bytes] = None
    ) -> None:
        self._reactor = reactor
        self._acceptable_protocols = [
            to_bytes(protocol) for protocol in acceptable_protocols
        ]
        self._context_factory = AcceptableProtocolsContextFactory(context_factory, self._acceptable_protocols)
        self._endpoint_factory = _StandardEndpointFactory(
            self._reactor, self._context_factory,
            connect_timeout, bind_address
        )

    def get_endpoint(self, uri: URI):
        return self._endpoint_factory.endpointForURI(uri)

    def negotiate(self, uri: URI) -> Deferred:
        """Returns a deferred which fires with the transport """
        d = Deferred()
        endpoint = self.get_endpoint(uri)
        factory = NegotiateProtocolFactory(self._acceptable_protocols, d)
        endpoint.connect(factory)
        return d


class HTTPNegotiateDownloadHandler:
    def __init__(self, settings: Settings, crawler=None):
        self._settings = settings
        self._crawler = crawler

        self.acceptable_protocols = []

        handlers_base = without_none_values(self._settings.get('HTTP_DOWNLOAD_HANDLERS_BASE'))
        self.handlers: Dict = {}
        for protocol, cls_path in handlers_base.items():
            self.acceptable_protocols.append(protocol)

            dh_cls = load_object(cls_path)
            self.handlers[protocol] = create_instance(
                objcls=dh_cls,
                settings=self._settings,
                crawler=self._crawler,
            )

        # Cache to store the protocol negotiated for all the
        # connections, in case we get a request with the same key,
        # new request can be immediately issued to the respective
        # download handler
        self._cache_connection = LocalCache(limit=10000)

        # Store off a list of all connections with the same key
        # This is used when there are multiple requests issued at the same time,
        # then we negotiate only one connection and pause all the other connections.
        # When the connection is made we issue all the paused requests with
        # respective download handler
        self._pending_connections: Dict[Tuple, Deque[Deferred]] = {}

        self._context_factory = load_context_factory_from_settings(settings, crawler)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler)

    def _parse_uri(self, url: str) -> URI:
        url = urldefrag(url)[0]
        return URI.fromBytes(to_bytes(url, encoding='ascii'))

    def _get_key(self, request: Request):
        uri = self._parse_uri(request.url)
        return uri.scheme, uri.host, uri.port

    def get_download_handler(self, protocol):
        return self.handlers.get(protocol)

    def _connection_established(self, key: Tuple, protocol: str) -> None:
        """We have established a connection with given key. Hence,
        we issue all the request to the negotiated protocol"""
        self._cache_connection.setdefault(key, protocol)
        download_handler = self.get_download_handler(protocol)
        connections = self._pending_connections.pop(key, None)
        while connections:
            d = connections.popleft()
            d.callback(download_handler)

        del connections

    def check_connection_exists(self, request: Request) -> Optional[Union[HTTP11DownloadHandler, H2DownloadHandler]]:
        """
        Using the pools in all of the download handlers, we check
        if a persistent connection to the request uri already exists.

        Apart from checking in the connection pools, all requests which are
        1. Using Proxy
        2. HTTP (insecure)
        are issued to the HTTP/1.1 download handler.

        Arguments:
            request -- Scrapy Request instance

        Returns:
            Respective download handler instance if it exists
            else None
        """
        key = self._get_key(request)

        if key in self._cache_connection:
            return self.get_download_handler(self._cache_connection[key])

        proxy = request.meta.get('proxy')

        # Check if http (without ssl/tls) request or proxy is required
        # Issue this request using the HTTP/1.x download handler
        if key[0] == b'http' or proxy:
            self._cache_connection.setdefault(key, 'http/1.1')
            return self.handlers['http/1.1']

        # Check in the order of the acceptable protocols list
        for protocol in self.acceptable_protocols:
            if (
                    key in self.handlers['http/1.1'].pool._connections
                    or key in self.handlers['h2'].pool.established_connections
                    or key in self.handlers['h2'].pool.pending_connections
                    or self._cache_connection.get(key, None) == protocol
            ):
                return self.get_download_handler(protocol)

        return None

    def add_connection(self, transport, request: Request) -> None:
        negotiated_protocol = transport.negotiatedProtocol.decode()
        key = self._get_key(request)
        uri = self._parse_uri(request.url)
        handler = self.handlers[negotiated_protocol]

        # Create an instance of the connection
        if negotiated_protocol == 'http/1.1':
            assert isinstance(handler, HTTP11DownloadHandler)

            def quiescent_callback(protocol):
                handler.pool._putConnection(key, protocol)

            conn = HTTP11ClientProtocol(quiescent_callback)
            transport.wrappedProtocol = conn
            conn.makeConnection(transport)
            handler.pool._putConnection(key, conn)
        else:  # 'h2' expected
            assert isinstance(handler, H2DownloadHandler)

            conn_lost_deferred = Deferred()
            conn_lost_deferred.addCallback(handler.pool._remove_connection, key)

            conn = H2ClientProtocol(uri, self._settings, conn_lost_deferred)
            transport.wrappedProtocol = conn
            conn.makeConnection(transport)
            handler.pool.put_connection(conn, key)

        self._connection_established(key, negotiated_protocol)

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        """ Working:
        1. Check if http --> Directly use HTTP/1.x
        2. Check if we already have a connection to the base-url
         Yes -> Utilize the connection
         No -> Got to 3.
        3. Check what's the negotiated protocol
         3.1 Meanwhile the protocol is negotiated save all the request instances
          having the same base URI (as they'll have same negotiated protocol)
         3.2 After negotiation is done, issue all the pending requests to the respective
          download handler
        4. Store the result (so that we don't have to look for negotiated protocol again?)
        5. Create a new instance of the respective protocol with the `transport` same as that
         of NegotiatedProtocol (use the same connection - switch protocol)
        """
        key = self._get_key(request)

        def make_request(_download_handler: Union[HTTP11DownloadHandler, H2DownloadHandler]):
            return _download_handler.download_request(request, spider)

        download_handler = self.check_connection_exists(request)
        if download_handler:
            # We already have a download handler with a cached connection
            return download_handler.download_request(request, spider)

        if key in self._pending_connections:
            d = Deferred()
            d.addCallback(make_request)
            self._pending_connections[key].append(d)
            return d

        # Connect to the negotiated protocol
        from twisted.internet import reactor
        agent = NegotiateAgent(
            reactor=reactor,
            acceptable_protocols=self.acceptable_protocols,
            context_factory=self._context_factory
        )
        conn_d = agent.negotiate(self._parse_uri(request.url))
        conn_d.addCallback(self.add_connection, request)

        # This the first request sent with this URI
        # We will wait until the connection is established
        # Then send the request instance to the negotiated protocol's
        # download handler pipeline
        d = Deferred()
        d.addCallback(make_request)
        self._pending_connections[key] = deque()
        self._pending_connections[key].append(d)
        return d

    def close(self) -> Deferred:
        self.handlers['h2'].close()
        return self.handlers['http/1.1'].close()
