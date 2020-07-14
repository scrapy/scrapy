from typing import Dict, Tuple, Optional

from twisted.internet import defer
from twisted.internet._sslverify import _setAcceptableProtocols, ClientTLSOptions
from twisted.internet.base import ReactorBase
from twisted.internet.defer import Deferred
from twisted.internet.endpoints import SSL4ClientEndpoint
from twisted.python.failure import Failure
from twisted.web.client import URI, BrowserLikePolicyForHTTPS, _StandardEndpointFactory
from twisted.web.iweb import IPolicyForHTTPS
from zope.interface import implementer
from zope.interface.verify import verifyObject

from scrapy.core.http2.protocol import H2ClientProtocol, H2ClientFactory
from scrapy.http.request import Request
from scrapy.settings import Settings


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
        conn_lost_deferred = Deferred()
        conn_lost_deferred.addCallback(self._remove_connection, key)

        factory = H2ClientFactory(uri, self.settings, conn_lost_deferred)
        d = endpoint.connect(factory)
        d.addCallback(self.put_connection, key)
        return d

    def put_connection(self, conn: H2ClientProtocol, key: Tuple) -> H2ClientProtocol:
        self._connections[key] = conn
        return conn

    def _remove_connection(self, reason: Failure, key: Tuple) -> None:
        self._connections.pop(key)


@implementer(IPolicyForHTTPS)
class H2WrappedContextFactory:
    def __init__(self, context_factory) -> None:
        verifyObject(IPolicyForHTTPS, context_factory)
        self._wrapped_context_factory = context_factory

    def creatorForNetloc(self, hostname, port) -> ClientTLSOptions:
        options = self._wrapped_context_factory.creatorForNetloc(hostname, port)
        _setAcceptableProtocols(options._ctx, [b'h2'])
        return options


class H2Agent:
    def __init__(
        self, reactor: ReactorBase, pool: H2ConnectionPool,
        context_factory=BrowserLikePolicyForHTTPS(),
        connect_timeout: Optional[float] = None, bind_address: Optional[bytes] = None
    ) -> None:
        self._reactor = reactor
        self._pool = pool
        self._context_factory = H2WrappedContextFactory(context_factory)
        self._endpoint_factory = _StandardEndpointFactory(
            self._reactor, self._context_factory,
            connect_timeout, bind_address
        )

    def request(self, request: Request) -> Deferred:
        uri = URI.fromBytes(bytes(request.url, encoding='utf-8'))
        endpoint = self._endpoint_factory.endpointForURI(uri)
        d = self._pool.get_connection(uri, endpoint)
        d.addCallback(lambda conn: conn.request(request))
        return d
