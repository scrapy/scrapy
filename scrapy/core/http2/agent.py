from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from twisted.internet import defer
from twisted.internet.defer import Deferred
from twisted.python.failure import Failure
from twisted.web.client import (
    URI,
    BrowserLikePolicyForHTTPS,
    ResponseFailed,
    _StandardEndpointFactory,
)
from twisted.web.error import SchemeNotSupported

from scrapy.core.downloader.contextfactory import AcceptableProtocolsContextFactory
from scrapy.core.http2.protocol import H2ClientFactory, H2ClientProtocol

if TYPE_CHECKING:
    from twisted.internet.base import ReactorBase
    from twisted.internet.endpoints import HostnameEndpoint

    from scrapy.http import Request, Response
    from scrapy.settings import Settings
    from scrapy.spiders import Spider


ConnectionKeyT = tuple[bytes, bytes, int]


class H2ConnectionPool:
    def __init__(self, reactor: ReactorBase, settings: Settings) -> None:
        self._reactor = reactor
        self.settings = settings

        # Store a dictionary which is used to get the respective
        # H2ClientProtocolInstance using the  key as Tuple(scheme, hostname, port)
        self._connections: dict[ConnectionKeyT, H2ClientProtocol] = {}

        # Save all requests that arrive before the connection is established
        self._pending_requests: dict[
            ConnectionKeyT, deque[Deferred[H2ClientProtocol]]
        ] = {}

    def get_connection(
        self, key: ConnectionKeyT, uri: URI, endpoint: HostnameEndpoint
    ) -> Deferred[H2ClientProtocol]:
        if key in self._pending_requests:
            # Received a request while connecting to remote
            # Create a deferred which will fire with the H2ClientProtocol
            # instance
            d: Deferred[H2ClientProtocol] = Deferred()
            self._pending_requests[key].append(d)
            return d

        # Check if we already have a connection to the remote
        conn = self._connections.get(key, None)
        if conn:
            # Return this connection instance wrapped inside a deferred
            return defer.succeed(conn)

        # No connection is established for the given URI
        return self._new_connection(key, uri, endpoint)

    def _new_connection(
        self, key: ConnectionKeyT, uri: URI, endpoint: HostnameEndpoint
    ) -> Deferred[H2ClientProtocol]:
        self._pending_requests[key] = deque()

        conn_lost_deferred: Deferred[list[BaseException]] = Deferred()
        conn_lost_deferred.addCallback(self._remove_connection, key)

        factory = H2ClientFactory(uri, self.settings, conn_lost_deferred)
        conn_d = endpoint.connect(factory)
        conn_d.addCallback(self.put_connection, key)

        d: Deferred[H2ClientProtocol] = Deferred()
        self._pending_requests[key].append(d)
        return d

    def put_connection(
        self, conn: H2ClientProtocol, key: ConnectionKeyT
    ) -> H2ClientProtocol:
        self._connections[key] = conn

        # Now as we have established a proper HTTP/2 connection
        # we fire all the deferred's with the connection instance
        pending_requests = self._pending_requests.pop(key, None)
        while pending_requests:
            d = pending_requests.popleft()
            d.callback(conn)

        return conn

    def _remove_connection(
        self, errors: list[BaseException], key: ConnectionKeyT
    ) -> None:
        self._connections.pop(key)

        # Call the errback of all the pending requests for this connection
        pending_requests = self._pending_requests.pop(key, None)
        while pending_requests:
            d = pending_requests.popleft()
            d.errback(ResponseFailed(errors))

    def close_connections(self) -> None:
        """Close all the HTTP/2 connections and remove them from pool

        Returns:
            Deferred that fires when all connections have been closed
        """
        for conn in self._connections.values():
            assert conn.transport is not None  # typing
            conn.transport.abortConnection()


class H2Agent:
    def __init__(
        self,
        reactor: ReactorBase,
        pool: H2ConnectionPool,
        context_factory: BrowserLikePolicyForHTTPS = BrowserLikePolicyForHTTPS(),
        connect_timeout: float | None = None,
        bind_address: bytes | None = None,
    ) -> None:
        self._reactor = reactor
        self._pool = pool
        self._context_factory = AcceptableProtocolsContextFactory(
            context_factory, acceptable_protocols=[b"h2"]
        )
        self.endpoint_factory = _StandardEndpointFactory(
            self._reactor, self._context_factory, connect_timeout, bind_address
        )

    def get_endpoint(self, uri: URI) -> HostnameEndpoint:
        return self.endpoint_factory.endpointForURI(uri)

    def get_key(self, uri: URI) -> ConnectionKeyT:
        """
        Arguments:
            uri - URI obtained directly from request URL
        """
        return uri.scheme, uri.host, uri.port

    def request(self, request: Request, spider: Spider) -> Deferred[Response]:
        uri = URI.fromBytes(bytes(request.url, encoding="utf-8"))
        try:
            endpoint = self.get_endpoint(uri)
        except SchemeNotSupported:
            return defer.fail(Failure())

        key = self.get_key(uri)
        d: Deferred[H2ClientProtocol] = self._pool.get_connection(key, uri, endpoint)
        d2: Deferred[Response] = d.addCallback(
            lambda conn: conn.request(request, spider)
        )
        return d2


class ScrapyProxyH2Agent(H2Agent):
    def __init__(
        self,
        reactor: ReactorBase,
        proxy_uri: URI,
        pool: H2ConnectionPool,
        context_factory: BrowserLikePolicyForHTTPS = BrowserLikePolicyForHTTPS(),
        connect_timeout: float | None = None,
        bind_address: bytes | None = None,
    ) -> None:
        super().__init__(
            reactor=reactor,
            pool=pool,
            context_factory=context_factory,
            connect_timeout=connect_timeout,
            bind_address=bind_address,
        )
        self._proxy_uri = proxy_uri

    def get_endpoint(self, uri: URI) -> HostnameEndpoint:
        return self.endpoint_factory.endpointForURI(self._proxy_uri)

    def get_key(self, uri: URI) -> ConnectionKeyT:
        """We use the proxy uri instead of uri obtained from request url"""
        return b"http-proxy", self._proxy_uri.host, self._proxy_uri.port
