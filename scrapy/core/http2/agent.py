from typing import Dict, Tuple

from twisted.internet import defer
from twisted.internet.base import ReactorBase
from twisted.internet.defer import Deferred
from twisted.internet.endpoints import SSL4ClientEndpoint, optionsForClientTLS
from twisted.web.client import URI, BrowserLikePolicyForHTTPS

from scrapy.core.http2.protocol import H2ClientProtocol, H2ClientFactory
from scrapy.http.request import Request
from scrapy.settings import Settings
from scrapy.utils.python import to_bytes, to_unicode


class H2ConnectionPool:
    def __init__(self, reactor: ReactorBase, settings: Settings) -> None:
        self._reactor = reactor
        self.settings = settings
        self._connections: Dict[Tuple, H2ClientProtocol] = {}

    def get_connection(self, uri: URI, endpoint: SSL4ClientEndpoint) -> Deferred:
        key = (uri.scheme, uri.host, uri.port)
        conn = self._connections.get(key, None)
        if conn:
            return defer.succeed(conn)
        return self._new_connection(key, uri, endpoint)

    def _new_connection(self, key: Tuple, uri: URI, endpoint: SSL4ClientEndpoint) -> Deferred:
        factory = H2ClientFactory(uri, self.settings)
        d = endpoint.connect(factory)

        def put_connection(conn: H2ClientProtocol) -> H2ClientProtocol:
            self._connections[key] = conn
            return conn

        d.addCallback(put_connection)
        return d

    def _remove_connection(self, key) -> None:
        conn = self._connections.pop(key)
        conn.loseConnection()


class H2Agent:
    def __init__(
        self, reactor: ReactorBase, pool: H2ConnectionPool,
        context_factory=BrowserLikePolicyForHTTPS()
    ) -> None:
        self._reactor = reactor
        self._pool = pool
        self._context_factory = context_factory

    def request(self, request: Request) -> Deferred:
        uri = URI.fromBytes(to_bytes(request.url, encoding='ascii'))
        # options = optionsForClientTLS(hostname=to_unicode(uri.host), acceptableProtocols=[b'h2'])
        # Hacky fix: Use options instead of self._context_factory to make endpoint work for HTTP/2
        endpoint = SSL4ClientEndpoint(self._reactor, to_unicode(uri.host), uri.port, self._context_factory)
        d = self._pool.get_connection(uri, endpoint)

        def cb_connected(conn: H2ClientProtocol):
            return conn.request(request)

        d.addCallback(cb_connected)
        return d
