from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from twisted.internet import defer
from twisted.internet.defer import Deferred
from twisted.python.failure import Failure
from twisted.web.client import URI, BrowserLikePolicyForHTTPS, _StandardEndpointFactory
from twisted.web.error import SchemeNotSupported

from scrapy.core.downloader.contextfactory import _AcceptableProtocolsContextFactory
from scrapy.core.http2.protocol import H2ClientFactory, H2ClientProtocol

if TYPE_CHECKING:
    from twisted.internet.base import ReactorBase
    from twisted.internet.endpoints import HostnameEndpoint

    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.spiders import Spider


ConnectionKeyT = tuple[bytes, bytes, int]


class H2ConnectionPool:
    def __init__(self, reactor: ReactorBase, crawler: Crawler, limit: int = 0) -> None:
        self._reactor = reactor
        self._crawler = crawler
        self._limit = limit

        # Store a dictionary which is used to get the respective
        # H2ClientProtocolInstance using the  key as Tuple(scheme, hostname, port)
        self._connections: dict[ConnectionKeyT, H2ClientProtocol] = {}

        # Save all requests that arrive before the connection is established
        self._pending_requests: dict[
            ConnectionKeyT, deque[Deferred[H2ClientProtocol]]
        ] = {}

        self._tls_verbose_logging: bool = crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )

    def get_connection(
        self, key: ConnectionKeyT, uri: URI, endpoint: HostnameEndpoint
    ) -> Deferred[H2ClientProtocol]:
        if key in self._pending_requests:
            # Received a request while connecting to remote
            return self._pending_request(key)

        # Check if we already have a usable connection to the remote, moving
        # it to the end so that the pool stays ordered from least to most
        # recently used
        conn = self._connections.get(key)
        if conn and not conn.closing:
            del self._connections[key]
            self._connections[key] = conn
            # Return this connection instance wrapped inside a deferred
            return defer.succeed(conn)

        # No connection is established for the given URI
        return self._new_connection(key, uri, endpoint)

    def _new_connection(
        self, key: ConnectionKeyT, uri: URI, endpoint: HostnameEndpoint
    ) -> Deferred[H2ClientProtocol]:
        self._enforce_limit()
        self._pending_requests[key] = deque()

        conn_lost_deferred: Deferred[list[BaseException]] = Deferred()

        factory = H2ClientFactory(
            uri,
            self._crawler,
            conn_lost_deferred,
            tls_verbose_logging=self._tls_verbose_logging,
        )
        conn_d = endpoint.connect(factory)
        d = self._pending_request(key)
        conn_d.addCallbacks(
            self.put_connection,
            self._connection_failed,
            callbackArgs=(key, conn_lost_deferred),
            errbackArgs=(key,),
        )
        return d

    def _pending_request(self, key: ConnectionKeyT) -> Deferred[H2ClientProtocol]:
        """Return a deferred that fires with the connection being established
        for *key*.

        Cancelling it takes it out of the queue, so that the connection, once
        established or found unreachable, only fires the deferreds of the
        requests that are still waiting for it.
        """
        pending_requests = self._pending_requests[key]
        d: Deferred[H2ClientProtocol] = Deferred(pending_requests.remove)
        pending_requests.append(d)
        return d

    def _enforce_limit(self) -> None:
        """Close the least recently used connections that are not serving any
        stream, to make room for one more connection.

        HTTP/2 multiplexes requests over a single connection per remote, so a
        connection with active streams is kept even if that leaves the pool
        over the limit.
        """
        if not self._limit:
            return
        surplus = len(self._connections) + len(self._pending_requests) + 1 - self._limit
        for key, conn in list(self._connections.items()):
            if surplus <= 0:
                return
            if conn.metadata["active_streams"]:
                continue
            del self._connections[key]
            conn.close_idle()
            surplus -= 1

    def put_connection(
        self,
        conn: H2ClientProtocol,
        key: ConnectionKeyT,
        conn_lost_deferred: Deferred[list[BaseException]],
    ) -> H2ClientProtocol:
        self._connections[key] = conn
        conn_lost_deferred.addCallback(self._remove_connection, key, conn)

        # Now as we have established a proper HTTP/2 connection
        # we fire all the deferred's with the connection instance
        pending_requests = self._pending_requests.pop(key, None)
        while pending_requests:
            d = pending_requests.popleft()
            d.callback(conn)

        return conn

    def _connection_failed(self, failure: Failure, key: ConnectionKeyT) -> None:
        """Fail the requests waiting for a connection that could not be
        established, and let a later request try to connect again."""
        pending_requests = self._pending_requests.pop(key)
        while pending_requests:
            d = pending_requests.popleft()
            d.errback(failure)

    def _remove_connection(
        self, errors: list[BaseException], key: ConnectionKeyT, conn: H2ClientProtocol
    ) -> None:
        # a newer connection may have taken over the key already
        if self._connections.get(key) is conn:
            del self._connections[key]

    def close_connections(self) -> None:
        """Close all the HTTP/2 connections and remove them from pool."""
        for conn in self._connections.values():
            assert conn.transport is not None  # typing
            conn.transport.abortConnection()


class H2Agent:
    def __init__(
        self,
        reactor: ReactorBase,
        pool: H2ConnectionPool,
        context_factory: BrowserLikePolicyForHTTPS = BrowserLikePolicyForHTTPS(),  # noqa: B008
        connect_timeout: float | None = None,
        bind_address: tuple[str, int] | None = None,
    ) -> None:
        self._reactor = reactor
        self._pool = pool
        self._context_factory = _AcceptableProtocolsContextFactory(
            context_factory, acceptable_protocols=[b"h2"]
        )
        self.endpoint_factory = _StandardEndpointFactory(
            self._reactor, self._context_factory, connect_timeout, bind_address
        )

    def get_endpoint(self, uri: URI) -> HostnameEndpoint:
        return self.endpoint_factory.endpointForURI(uri)  # type: ignore[no-any-return]

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
