"""Download handlers for http and https schemes"""

from __future__ import annotations

import ipaddress
import logging
import re
from contextlib import suppress
from functools import partial
from io import BytesIO
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, BinaryIO, NotRequired, TypedDict, TypeVar, cast
from urllib.parse import urldefrag

from twisted.internet import ssl
from twisted.internet.defer import Deferred, succeed
from twisted.internet.endpoints import (
    HostnameEndpoint,
    TCP6ClientEndpoint,
    wrapClientTLS,
)
from twisted.internet.interfaces import IStreamClientEndpoint
from twisted.internet.protocol import ClientFactory, Factory, Protocol, connectionDone
from twisted.python.failure import Failure
from twisted.web._newclient import (
    HEADER,
    STATUS,
    HTTP11ClientProtocol,
    HTTPClientParser,
)
from twisted.web.client import (
    URI,
    Agent,
    HTTPConnectionPool,
    ResponseDone,
    ResponseFailed,
    _HTTP11ClientFactory,
)
from twisted.web.client import Response as TxResponse
from twisted.web.http import PotentialDataLoss, _DataLoss
from twisted.web.http_headers import Headers as TxHeaders
from twisted.web.iweb import UNKNOWN_LENGTH, IBodyProducer, IPolicyForHTTPS, IResponse
from zope.interface import implementer

from scrapy import Request, signals
from scrapy.core.downloader._idna_patch import _install_twisted_idna_fallbacks
from scrapy.core.downloader.contextfactory import _load_context_factory_from_settings
from scrapy.exceptions import (
    DownloadCancelledError,
    DownloadTimeoutError,
    NotConfigured,
    ResponseDataLossError,
    StopDownload,
)
from scrapy.http import Headers, Response
from scrapy.utils._download_handlers import (
    check_stop_download,
    get_dataloss_msg,
    get_maxsize_msg,
    get_proxy_headers,
    get_warnsize,
    get_warnsize_msg,
    make_response,
    normalize_bind_address,
    wrap_twisted_exceptions,
)
from scrapy.utils._ssl import _log_ssl_conn_debug_info
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.deprecate import warn_on_deprecated_spider_attribute
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.url import _add_http_if_no_scheme

from ._base_http import BaseHttpDownloadHandler

if TYPE_CHECKING:
    import os
    from collections.abc import Callable

    from twisted.internet.base import ReactorBase
    from twisted.internet.interfaces import IAddress, IConsumer, IProtocol
    from twisted.web._newclient import Request as TxRequest

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class _ResultT(TypedDict):
    txresponse: TxResponse
    body: NotRequired[bytes]
    flags: NotRequired[list[str] | None]
    certificate: NotRequired[ssl.Certificate | None]
    ip_address: NotRequired[ipaddress.IPv4Address | ipaddress.IPv6Address | None]
    stop_download: NotRequired[StopDownload | None]


class _LenientHTTPClientParser(HTTPClientParser):
    """Response parser that skips bad response header lines, those with no
    colon in them, instead of failing to parse the whole response.

    Some servers send such lines, and web browsers skip them and keep parsing
    the header lines that follow. See
    https://github.com/scrapy/scrapy/issues/210.
    """

    def lineReceived(self, line: bytes) -> None:
        # A copy of twisted.web._newclient.HTTPParser.lineReceived() where the
        # header name and value are only extracted from header lines that have
        # a colon.

        # Handle the normal CR LF case.
        line = line.removesuffix(b"\r")

        if self.state == STATUS:
            self.statusReceived(line)  # type: ignore[no-untyped-call]
            self.state = HEADER
            return

        # HEADER is the only other state in which lines are received, as the
        # parser switches to raw mode for the response body.
        if not line or line[0] not in b" \t":
            if self._partialHeader is not None:
                header = b"".join(self._partialHeader)
                if b":" in header:
                    name, value = header.split(b":", 1)
                    self.headerReceived(name, value.strip())  # type: ignore[no-untyped-call]
                else:
                    logger.debug(
                        f"Skipping the bad response header line {header!r}, as "
                        f"it has no colon."
                    )
            if not line:
                # Empty line means the header section is over.
                self.allHeadersReceived()  # type: ignore[no-untyped-call]
            else:
                # Line not beginning with LWS is another header.
                self._partialHeader = [line]
        else:
            # A line beginning with LWS is a continuation of a header begun on
            # a previous line.
            self._partialHeader.append(line)  # type: ignore[union-attr]


class _LenientHTTP11ClientProtocol(HTTP11ClientProtocol):
    """Protocol that parses responses with :class:`_LenientHTTPClientParser`."""

    def request(self, request: TxRequest) -> Deferred[IResponse]:
        d: Deferred[IResponse] = super().request(request)
        # HTTP11ClientProtocol.request() hardcodes the parser class, so the
        # only way to use a different one is to replace the class of the parser
        # object that it creates. This is safe because
        # _LenientHTTPClientParser defines no additional state. The parser is
        # always there because HTTPConnectionPool only reuses connections whose
        # protocol is in the QUIESCENT state, for which request() always
        # creates a parser.
        assert self._parser is not None
        self._parser.__class__ = _LenientHTTPClientParser

        # For responses without a body, twisted.web.client.Response never
        # hands its transport to a protocol, so the certificate and IP
        # address cannot be read from it later (see
        # _ResponseReader.connectionMade). self.transport, however, is the
        # connection's real transport and outlives any single request, so
        # read the certificate and IP address from it directly and stash
        # them on the response.
        assert self.transport is not None
        transport = self.transport

        def _attach_connection_info(response: IResponse) -> IResponse:
            with suppress(AttributeError):
                response._scrapy_certificate = ssl.Certificate(
                    transport.getPeerCertificate()
                )
            with suppress(AttributeError):
                response._scrapy_ip_address = ipaddress.ip_address(
                    transport.getPeer().host
                )
            return response

        d.addCallback(_attach_connection_info)
        return d


class _TrackedHTTP11ClientProtocol(_LenientHTTP11ClientProtocol):
    """Connection that tells the pool that opened it when it closes, whether it
    was cached at the time or in use."""

    _pool: _BoundedHTTPConnectionPool
    _pool_key: Any

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        self._pool._forget(self)
        super().connectionLost(reason)  # type: ignore[no-untyped-call]


class _BoundedHTTP11ClientFactory(_HTTP11ClientFactory):
    noisy = False

    def __init__(
        self,
        quiescentCallback: Callable[[HTTP11ClientProtocol], None],
        metadata: str,
        pool: _BoundedHTTPConnectionPool,
        key: Any,
    ):
        super().__init__(quiescentCallback, metadata)  # type: ignore[no-untyped-call]
        self._pool: _BoundedHTTPConnectionPool = pool
        self._key: Any = key

    def buildProtocol(self, addr: IAddress | None) -> _TrackedHTTP11ClientProtocol:
        protocol = _TrackedHTTP11ClientProtocol(self._quiescentCallback)  # type: ignore[no-untyped-call]
        protocol._pool = self._pool
        protocol._pool_key = self._key
        self._pool._open.add(protocol)
        return protocol


class _BoundedHTTPConnectionPool(HTTPConnectionPool):
    """Connection pool that keeps the number of open connections, cached and in
    use alike, under *limit*, where 0 means no limit.

    Opening a connection once the limit is reached closes the least recently
    used cached connection to make room for it. When there is no cached
    connection left to close, the limit is exceeded rather than requests
    delayed.
    """

    _factory = _BoundedHTTP11ClientFactory  # type: ignore[assignment]

    def __init__(self, reactor: ReactorBase, limit: int, keepalive_timeout: float):
        super().__init__(reactor, persistent=bool(keepalive_timeout))  # type: ignore[no-untyped-call]
        self.cachedConnectionTimeout = keepalive_timeout  # type: ignore[assignment]
        self._limit: int = limit
        self._open: set[_TrackedHTTP11ClientProtocol] = set()

    def _newConnection(
        self, key: Any, endpoint: IStreamClientEndpoint
    ) -> Deferred[HTTP11ClientProtocol]:
        while self._limit and len(self._open) >= self._limit and self._evict():
            pass

        def quiescentCallback(protocol: HTTP11ClientProtocol) -> None:
            self._putConnection(key, protocol)  # type: ignore[no-untyped-call]

        factory = self._factory(quiescentCallback, repr(endpoint), self, key)
        return endpoint.connect(factory)  # type: ignore[no-any-return]

    def _forget(self, connection: _TrackedHTTP11ClientProtocol) -> None:
        self._open.discard(connection)

    def _evict(self) -> bool:
        """Close the least recently used cached connection, and report whether
        there was one to close.

        ``_timeouts`` holds cached connections only, and ``getConnection()``
        drops the ones it hands out, so its insertion order goes from least to
        most recently used.
        """
        connection = next(iter(self._timeouts), None)
        if connection is None:
            return False
        self._timeouts[connection].cancel()
        # dropped early so that a caller looping on this method sees the room
        # made by connections that have yet to finish closing
        self._forget(connection)
        key = connection._pool_key
        self._removeConnection(key, connection)  # type: ignore[no-untyped-call]
        if not self._connections[key]:
            del self._connections[key]
        return True


class HTTP11DownloadHandler(BaseHttpDownloadHandler):
    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("TWISTED_REACTOR_ENABLED"):
            raise NotConfigured(f"{type(self).__name__} requires a Twisted reactor.")
        _install_twisted_idna_fallbacks()
        super().__init__(crawler)
        self._crawler = crawler

        from twisted.internet import reactor

        self._pool: _BoundedHTTPConnectionPool = _BoundedHTTPConnectionPool(
            reactor, self._pool_size_total, self._keepalive_timeout
        )
        self._pool.maxPersistentPerHost = self._pool_size_per_host

        self._contextFactory: IPolicyForHTTPS = _load_context_factory_from_settings(
            crawler
        )
        self._bind_address = crawler.settings.get("DOWNLOAD_BIND_ADDRESS")
        self._disconnect_timeout: int = 1

    async def download_request(self, request: Request) -> Response:
        if hasattr(self._crawler.spider, "download_maxsize"):  # pragma: no cover
            warn_on_deprecated_spider_attribute("download_maxsize", "DOWNLOAD_MAXSIZE")
        if hasattr(self._crawler.spider, "download_warnsize"):  # pragma: no cover
            warn_on_deprecated_spider_attribute(
                "download_warnsize", "DOWNLOAD_WARNSIZE"
            )

        agent = _ScrapyAgent(
            contextFactory=self._contextFactory,
            bindAddress=self._bind_address,
            pool=self._pool,
            maxsize=getattr(
                self._crawler.spider, "download_maxsize", self._default_maxsize
            ),
            warnsize=getattr(
                self._crawler.spider, "download_warnsize", self._default_warnsize
            ),
            fail_on_dataloss=self._fail_on_dataloss,
            crawler=self._crawler,
            tls_verbose_logging=self._tls_verbose_logging,
        )
        try:
            with wrap_twisted_exceptions():
                return await maybe_deferred_to_future(agent.download_request(request))
        except ResponseDataLossError:
            if not self._fail_on_dataloss_warned:
                logger.warning(get_dataloss_msg(request.url))
                self._fail_on_dataloss_warned = True
            raise

    async def close(self) -> None:
        from twisted.internet import reactor

        d: Deferred[None] = self._pool.closeCachedConnections()  # type: ignore[no-untyped-call]
        # closeCachedConnections will hang on network or server issues, so
        # we'll manually timeout the deferred.
        #
        # Twisted issue addressing this problem can be found here:
        # https://github.com/twisted/twisted/issues/7738
        #
        # closeCachedConnections doesn't handle external errbacks, so we'll
        # issue a callback after `_disconnect_timeout` seconds.
        #
        # See also https://github.com/scrapy/scrapy/issues/2653
        delayed_call = reactor.callLater(self._disconnect_timeout, d.callback, ())

        try:
            await maybe_deferred_to_future(d)
        finally:
            # Only inactive if the timeout above won the race, which the tests
            # cannot force.
            if delayed_call.active():  # pragma: no branch
                delayed_call.cancel()


class TunnelError(Exception):
    """An HTTP CONNECT tunnel could not be established by the proxy."""


def _is_ipv6_literal(host: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address)
    except ValueError:  # a hostname
        return False


class _TunnelProtocol(Protocol):
    """Sends an HTTP CONNECT request to a proxy and, once the tunnel is open,
    hands the connection over to a wrapped protocol.

    It plays the role of Twisted's ``_WrappingProtocol`` but performs a CONNECT
    handshake before connecting the wrapped protocol. The wrapped protocol is
    the destination TLS protocol, so its handshake is negotiated inside the
    tunnel; when the proxy itself is reached over TLS this results in a
    TLS-in-TLS connection.
    """

    _truncatedLength = 1000
    _responseAnswer = (
        r"HTTP/1\.. (?P<status>\d{3})(?P<reason>.{," + str(_truncatedLength) + r"})"
    )
    _responseMatcher = re.compile(_responseAnswer.encode())

    def __init__(
        self,
        connectedDeferred: Deferred[IProtocol],
        wrappedProtocol: IProtocol,
        host: bytes,
        port: int,
        proxyHost: str,
        proxyPort: int,
        proxyHeaders: tuple[tuple[str, str], ...] = (),
    ):
        self._connectedDeferred = connectedDeferred
        self._wrappedProtocol = wrappedProtocol
        self._host = host
        self._port = port
        self._proxyHost = proxyHost
        self._proxyPort = proxyPort
        self._proxyHeaders = proxyHeaders
        self._connectBuffer: bytearray = bytearray()
        self._tunnelReady = False

    @staticmethod
    def _format_host(host: bytes) -> bytes:
        """Return *host* as it goes into the authority of the CONNECT request,
        i.e. with square brackets around IPv6 literals.
        """
        # URI.host strips the brackets of IPv6 literals, and only those contain
        # colons.
        return b"[" + host + b"]" if b":" in host else host

    def logPrefix(self) -> str:
        return type(self._wrappedProtocol).__name__

    def connectionMade(self) -> None:
        """Asks the proxy to open a tunnel."""
        assert self.transport
        self.transport.write(
            _tunnel_request_data(
                self._format_host(self._host), self._port, self._proxyHeaders
            )
        )

    def dataReceived(self, data: bytes) -> None:
        if self._tunnelReady:
            self._wrappedProtocol.dataReceived(data)
            return
        if self._connectedDeferred.called:
            # The tunnel was cancelled while waiting for the CONNECT response.
            return
        self._connectBuffer += data
        # make sure that enough (all) bytes are consumed
        # and that we've got all HTTP headers (ending with a blank line)
        # from the proxy so that we don't send those bytes to the TLS layer
        #
        # see https://github.com/scrapy/scrapy/issues/2491
        if b"\r\n\r\n" not in self._connectBuffer:
            return
        header, _, remaining = bytes(self._connectBuffer).partition(b"\r\n\r\n")
        respm = self._responseMatcher.match(header)
        if respm and int(respm.group("status")) == 200:
            self._tunnelReady = True
            # Hand the connection over to the wrapped (destination TLS)
            # protocol, which starts its handshake through the tunnel.
            assert self.transport is not None
            self._wrappedProtocol.makeConnection(self.transport)
            self._connectedDeferred.callback(self._wrappedProtocol)
            if remaining:
                self._wrappedProtocol.dataReceived(remaining)
        else:
            extra: Any
            if respm:
                extra = {
                    "status": int(respm.group("status")),
                    "reason": respm.group("reason").strip(),
                }
            else:
                extra = header[: self._truncatedLength]
            self._connectedDeferred.errback(
                TunnelError(
                    "Could not open CONNECT tunnel with proxy "
                    f"{self._proxyHost}:{self._proxyPort} [{extra!r}]"
                )
            )

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        if self._tunnelReady:
            self._wrappedProtocol.connectionLost(reason)
        elif not self._connectedDeferred.called:
            # The connection was lost before the tunnel was established (e.g.
            # the proxy closed the connection in response to CONNECT).
            self._connectedDeferred.errback(reason)


class _TunnelFactory(ClientFactory):
    """Builds :class:`_TunnelProtocol` instances wrapping the protocols built
    by another factory."""

    def __init__(
        self,
        connectedDeferred: Deferred[IProtocol],
        wrappedFactory: Factory,
        host: bytes,
        port: int,
        proxyHost: str,
        proxyPort: int,
        proxyHeaders: tuple[tuple[str, str], ...] = (),
    ):
        self._connectedDeferred = connectedDeferred
        self._wrappedFactory = wrappedFactory
        self._host = host
        self._port = port
        self._proxyHost = proxyHost
        self._proxyPort = proxyPort
        self._proxyHeaders = proxyHeaders

    def doStart(self) -> None:
        self._wrappedFactory.doStart()

    def doStop(self) -> None:
        self._wrappedFactory.doStop()

    def buildProtocol(self, addr: IAddress) -> _TunnelProtocol:
        wrappedProtocol = self._wrappedFactory.buildProtocol(addr)
        # The wrapped factory is always the destination TLS factory built by
        # wrapClientTLS, whose buildProtocol never returns None.
        assert wrappedProtocol is not None
        return _TunnelProtocol(
            self._connectedDeferred,
            wrappedProtocol,
            self._host,
            self._port,
            self._proxyHost,
            self._proxyPort,
            self._proxyHeaders,
        )


@implementer(IStreamClientEndpoint)
class _TunnelEndpoint:
    """A wrapper endpoint that opens an HTTP CONNECT tunnel over the connection
    established by the wrapped endpoint before delivering it to the protocol
    factory.

    The wrapped endpoint connects to the proxy (over plain TCP for ``http://``
    proxies, or over TLS via :func:`~twisted.internet.endpoints.wrapClientTLS`
    for ``https://`` proxies). Wrapping this endpoint in turn with
    ``wrapClientTLS`` negotiates the destination TLS session inside the tunnel.
    """

    def __init__(
        self,
        wrappedEndpoint: IStreamClientEndpoint,
        host: bytes,
        port: int,
        proxyHost: str,
        proxyPort: int,
        proxyHeaders: tuple[tuple[str, str], ...] = (),
    ):
        self._wrappedEndpoint = wrappedEndpoint
        self._host = host
        self._port = port
        self._proxyHost = proxyHost
        self._proxyPort = proxyPort
        self._proxyHeaders = proxyHeaders

    def connect(self, protocolFactory: Factory) -> Deferred[IProtocol]:
        proxyProtocol: IProtocol | None = None

        def proxyConnected(protocol: IProtocol) -> None:
            nonlocal proxyProtocol
            proxyProtocol = protocol

        def cancel(_: Deferred[IProtocol]) -> None:
            # Tear down the connection to the proxy, e.g. on a download timeout.
            if proxyProtocol is None:
                # Still connecting to the proxy. This errbacks
                # connectedDeferred through _connectFailed().
                proxyDeferred.cancel()
            else:
                assert isinstance(proxyProtocol, _TunnelProtocol)
                assert proxyProtocol.transport
                proxyProtocol.transport.loseConnection()

        connectedDeferred: Deferred[IProtocol] = Deferred(cancel)
        tunnelFactory = _TunnelFactory(
            connectedDeferred,
            protocolFactory,
            self._host,
            self._port,
            self._proxyHost,
            self._proxyPort,
            self._proxyHeaders,
        )
        proxyDeferred = self._wrappedEndpoint.connect(tunnelFactory)
        proxyDeferred.addCallbacks(
            proxyConnected, self._connectFailed, errbackArgs=(connectedDeferred,)
        )
        return connectedDeferred

    @staticmethod
    def _connectFailed(
        failure: Failure, connectedDeferred: Deferred[IProtocol]
    ) -> None:
        # Reached only when connecting to the proxy fails, i.e. before the
        # tunnel deferred has been fired.
        connectedDeferred.errback(failure)


def _tunnel_request_data(
    host: bytes, port: int, proxy_headers: tuple[tuple[str, str], ...] = ()
) -> bytes:
    r"""
    Return binary content of a CONNECT request.

    >>> _tunnel_request_data(b"example.com", 8080).decode()
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\n\r\n'
    >>> _tunnel_request_data(b"example.com", 8080, (("Proxy-Authorization", "123"),)).decode()
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\nProxy-Authorization: 123\r\n\r\n'
    """
    host_value = host + b":" + str(port).encode()
    tunnel_req = b"CONNECT " + host_value + b" HTTP/1.1\r\n"
    tunnel_req += b"Host: " + host_value + b"\r\n"
    for name, value in proxy_headers:
        tunnel_req += name.encode() + b": " + value.encode() + b"\r\n"
    tunnel_req += b"\r\n"
    return tunnel_req


class _BindAddressAgent(Agent):
    """An Agent that adds the configured local bind address to the
    connection pool key, so pooled connections are not shared between
    requests bound to different addresses."""

    def __init__(
        self,
        reactor: ReactorBase,
        contextFactory: IPolicyForHTTPS,
        connectTimeout: float | None = None,
        bindAddress: tuple[str, int] | None = None,
        pool: HTTPConnectionPool | None = None,
    ):
        super().__init__(reactor, contextFactory, connectTimeout, bindAddress, pool)  # type: ignore[no-untyped-call]

    def _requestWithEndpoint(
        self,
        key: tuple[Any, ...],
        endpoint: IStreamClientEndpoint,
        method: bytes,
        parsedURI: URI,
        headers: TxHeaders | None,
        bodyProducer: IBodyProducer | None,
        requestPath: bytes,
    ) -> Deferred[IResponse]:
        key += (self._endpointFactory._bindAddress,)
        return super()._requestWithEndpoint(
            key, endpoint, method, parsedURI, headers, bodyProducer, requestPath
        )


class _TunnelingAgent(_BindAddressAgent):
    """An agent that tunnels HTTPS downloads through a proxy using HTTP
    CONNECT. It may look strange that we have chosen to subclass Agent and not
    ProxyAgent but consider that after the tunnel is opened the proxy is
    transparent to the client; thus the agent should behave like there is no
    proxy involved.

    ``proxyConf`` is a ``(host, port, headers, tls)`` tuple, where ``tls``
    indicates whether the connection to the proxy itself must be made over TLS
    (an ``https://`` proxy). When it is, the destination TLS session runs inside
    the proxy TLS session (TLS-in-TLS).
    """

    def __init__(
        self,
        *,
        reactor: ReactorBase,
        proxyConf: tuple[str, int, tuple[tuple[str, str], ...], bool],
        contextFactory: IPolicyForHTTPS,
        connectTimeout: float | None = None,
        bindAddress: tuple[str, int] | None = None,
        pool: HTTPConnectionPool | None = None,
    ):
        super().__init__(reactor, contextFactory, connectTimeout, bindAddress, pool)
        self._proxyConf: tuple[str, int, tuple[tuple[str, str], ...], bool] = proxyConf
        self._contextFactory: IPolicyForHTTPS = contextFactory

    def _getEndpoint(self, uri: URI) -> IStreamClientEndpoint:
        proxyHost, proxyPort, proxyHeaders, proxyTLS = self._proxyConf
        timeout = self._endpointFactory._connectTimeout
        bindAddress = self._endpointFactory._bindAddress
        # Reach a proxy given as a name through a HostnameEndpoint, the same
        # endpoint Twisted's Agent uses: it resolves the name with
        # reactor.nameResolver and picks the address family from the result, so
        # proxies that only have AAAA records work, given an IPv6-capable
        # TWISTED_DNS_RESOLVER. A literal IPv6 address skips name resolution
        # instead, as the default resolver would fail to resolve it.
        endpoint: IStreamClientEndpoint = (
            TCP6ClientEndpoint(
                self._reactor, proxyHost, proxyPort, timeout, bindAddress
            )
            if _is_ipv6_literal(proxyHost)
            else HostnameEndpoint(
                self._reactor,
                proxyHost,
                proxyPort,
                timeout=timeout,
                bindAddress=bindAddress,
            )
        )
        if proxyTLS:
            # Set up TLS with the proxy itself, so that the CONNECT request and
            # the tunneled traffic are sent over it (TLS-in-TLS).
            proxyCreator = self._contextFactory.creatorForNetloc(  # type: ignore[call-arg,misc]
                proxyHost.encode("ascii"),  # type: ignore[arg-type]
                proxyPort,
            )
            endpoint = wrapClientTLS(proxyCreator, endpoint)
        endpoint = _TunnelEndpoint(
            endpoint, uri.host, uri.port, proxyHost, proxyPort, proxyHeaders
        )
        # Set proper Server Name Indication extension for the destination.
        destCreator = self._contextFactory.creatorForNetloc(  # type: ignore[call-arg,misc]
            uri.host,
            uri.port,
        )
        return wrapClientTLS(destCreator, endpoint)

    def _requestWithEndpoint(
        self,
        key: Any,
        endpoint: IStreamClientEndpoint,
        method: bytes,
        parsedURI: URI,
        headers: TxHeaders | None,
        bodyProducer: IBodyProducer | None,
        requestPath: bytes,
    ) -> Deferred[IResponse]:
        # the proxy host and port and the headers sent to the proxy are part of
        # the HTTP pool `key`, otherwise a request for the same remote host
        # could reuse a tunnel that was opened through a different proxy or
        # with different proxy headers
        key += self._proxyConf
        return super()._requestWithEndpoint(
            key=key,
            endpoint=endpoint,
            method=method,
            parsedURI=parsedURI,
            headers=headers,
            bodyProducer=bodyProducer,
            requestPath=requestPath,
        )


class _ScrapyProxyAgent(_BindAddressAgent):
    def __init__(
        self,
        reactor: ReactorBase,
        proxyURI: bytes,
        contextFactory: IPolicyForHTTPS,
        connectTimeout: float | None = None,
        bindAddress: tuple[str, int] | None = None,
        pool: HTTPConnectionPool | None = None,
    ):
        super().__init__(
            reactor=reactor,
            contextFactory=contextFactory,
            connectTimeout=connectTimeout,
            bindAddress=bindAddress,
            pool=pool,
        )
        self._proxyURI: URI = URI.fromBytes(proxyURI)

    def request(
        self,
        method: bytes,
        uri: bytes,
        headers: TxHeaders | None = None,
        bodyProducer: IBodyProducer | None = None,
    ) -> Deferred[IResponse]:
        """
        Issue a new request via the configured proxy.
        """
        # Cache *all* connections under the same key, since we are only
        # connecting to a single destination, the proxy:
        return self._requestWithEndpoint(
            key=(b"http-proxy", self._proxyURI.host, self._proxyURI.port),
            endpoint=self._getEndpoint(self._proxyURI),  # type: ignore[no-untyped-call]
            method=method,
            parsedURI=URI.fromBytes(uri),
            headers=headers,
            bodyProducer=bodyProducer,
            requestPath=uri,
        )


class _ScrapyAgent:
    def __init__(
        self,
        *,
        contextFactory: IPolicyForHTTPS,
        connectTimeout: float = 10,
        bindAddress: str | tuple[str, int] | None = None,
        pool: HTTPConnectionPool | None = None,
        maxsize: int = 0,
        warnsize: int = 0,
        fail_on_dataloss: bool = True,
        crawler: Crawler,
        tls_verbose_logging: bool = False,
    ):
        self._contextFactory: IPolicyForHTTPS = contextFactory
        self._connectTimeout: float = connectTimeout
        self._bindAddress: str | tuple[str, int] | None = bindAddress
        self._pool: HTTPConnectionPool | None = pool
        self._maxsize: int = maxsize
        self._warnsize: int = warnsize
        self._fail_on_dataloss: bool = fail_on_dataloss
        self._txresponse: TxResponse | None = None
        self._crawler: Crawler = crawler
        self._tls_verbose_logging: bool = tls_verbose_logging

    def _get_agent(self, request: Request, timeout: float) -> Agent:
        from twisted.internet import reactor

        bindaddress = request.meta.get("bindaddress") or self._bindAddress
        bindaddress = normalize_bind_address(bindaddress)
        proxy = request.meta.get("proxy")
        if proxy:
            proxy = _add_http_if_no_scheme(proxy)
            proxy_parsed = urlparse_cached(proxy)
            proxy_host = proxy_parsed.hostname
            proxy_port = proxy_parsed.port
            if not proxy_port:
                proxy_port = 443 if proxy_parsed.scheme == "https" else 80
            if urlparse_cached(request).scheme == "https":
                assert proxy_host is not None
                proxy_headers = get_proxy_headers(request)
                proxyAuth = request.headers.get(b"Proxy-Authorization", None)
                if proxyAuth and not any(
                    name == "Proxy-Authorization" for name, _ in proxy_headers
                ):
                    proxy_headers = (
                        ("Proxy-Authorization", proxyAuth.decode()),
                        *proxy_headers,
                    )
                proxyConf = (
                    proxy_host,
                    proxy_port,
                    proxy_headers,
                    proxy_parsed.scheme == "https",
                )
                return _TunnelingAgent(
                    reactor=reactor,
                    proxyConf=proxyConf,
                    contextFactory=self._contextFactory,
                    connectTimeout=timeout,
                    bindAddress=bindaddress,
                    pool=self._pool,
                )
            return _ScrapyProxyAgent(
                reactor=reactor,
                proxyURI=proxy.encode("ascii"),
                contextFactory=self._contextFactory,
                connectTimeout=timeout,
                bindAddress=bindaddress,
                pool=self._pool,
            )

        return _BindAddressAgent(
            reactor=reactor,
            contextFactory=self._contextFactory,
            connectTimeout=timeout,
            bindAddress=bindaddress,
            pool=self._pool,
        )

    def download_request(self, request: Request) -> Deferred[Response]:
        from twisted.internet import reactor

        timeout = request.meta.get("download_timeout") or self._connectTimeout
        agent = self._get_agent(request, timeout)

        # request details
        url = urldefrag(request.url)[0]
        method = request.method.encode()
        headers = TxHeaders(request.headers)
        if isinstance(agent, _TunnelingAgent):
            headers.removeHeader(b"Proxy-Authorization")
        elif isinstance(agent, _ScrapyProxyAgent):
            # without a tunnel the proxy reads the request headers, so the
            # headers meant for it travel among them, and it is up to the proxy
            # not to pass them on to the target server
            for name, value in get_proxy_headers(request):
                headers.addRawHeader(name, value)
        bodyproducer = _RequestBodyProducer(request.body) if request.body else None
        body_file = request.meta.get("body_file")
        bodybuf: BinaryIO = Path(body_file).open("wb") if body_file else BytesIO()
        start_time = monotonic()
        d: Deferred[IResponse] = agent.request(
            method,
            url.encode("ascii"),
            headers,
            cast("IBodyProducer", bodyproducer),
        )
        # set download latency
        d.addCallback(self._cb_latency, request, start_time)
        # response body is ready to be consumed
        d2: Deferred[_ResultT] = d.addCallback(self._cb_bodyready, request, bodybuf)
        d3: Deferred[Response] = d2.addCallback(self._cb_bodydone, url, body_file)
        # check download timeout
        self._timeout_cl = reactor.callLater(timeout, self._cb_timed_out, d3, request)
        d3.addBoth(self._cb_timeout, request, url, timeout)
        d3.addBoth(self._cb_close, bodybuf)
        return d3

    @staticmethod
    def _cb_close(result: _T, bodybuf: BinaryIO) -> _T:
        bodybuf.close()
        return result

    def _cb_timed_out(self, d3: Deferred[Response], request: Request) -> None:
        fail_on_dataloss = request.meta.get(
            "download_fail_on_dataloss", self._fail_on_dataloss
        )
        if not fail_on_dataloss and self._txresponse is not None:
            # let the response be delivered as a partial one instead of
            # cancelling the request outright
            self._txresponse._transport.stopProducing()
        else:
            d3.cancel()

    def _cb_timeout(self, result: _T, request: Request, url: str, timeout: float) -> _T:
        if self._timeout_cl.active():
            self._timeout_cl.cancel()
            return result
        # needed for HTTPS requests, otherwise _ResponseReader doesn't
        # receive connectionLost()
        if self._txresponse:
            self._txresponse._transport.stopProducing()

        if not isinstance(result, Failure):
            return result

        raise DownloadTimeoutError(f"Getting {url} took longer than {timeout} seconds.")

    def _cb_latency(self, result: _T, request: Request, start_time: float) -> _T:
        request.meta["download_latency"] = monotonic() - start_time
        return result

    @staticmethod
    def _headers_from_twisted_response(response: TxResponse) -> Headers:
        headers = Headers()
        if response.length != UNKNOWN_LENGTH:
            headers[b"Content-Length"] = str(response.length).encode()
        headers.update(response.headers.getAllRawHeaders())
        return headers

    def _cb_bodyready(
        self, txresponse: TxResponse, request: Request, bodybuf: BinaryIO
    ) -> _ResultT | Deferred[_ResultT]:
        if stop_download := check_stop_download(
            signals.headers_received,
            self._crawler,
            request,
            headers=self._headers_from_twisted_response(txresponse),
            body_length=txresponse.length,
        ):
            txresponse._transport.stopProducing()
            txresponse._transport.loseConnection()
            return {
                "txresponse": txresponse,
                "stop_download": stop_download,
            }

        # deliverBody hangs for responses without body
        if cast("int", txresponse.length) == 0:
            return {
                "txresponse": txresponse,
                "certificate": getattr(txresponse, "_scrapy_certificate", None),
                "ip_address": getattr(txresponse, "_scrapy_ip_address", None),
            }

        maxsize = request.meta.get("download_maxsize", self._maxsize)
        warnsize = get_warnsize(request.meta, self._warnsize)
        expected_size = (
            cast("int", txresponse.length)
            if txresponse.length != UNKNOWN_LENGTH
            else -1
        )
        fail_on_dataloss = request.meta.get(
            "download_fail_on_dataloss", self._fail_on_dataloss
        )

        if maxsize and expected_size > maxsize:
            warning_msg = get_maxsize_msg(
                expected_size, maxsize, request, expected=True
            )
            logger.warning(warning_msg)
            # Abort connection immediately.
            txresponse._transport._producer.abortConnection()
            raise DownloadCancelledError(warning_msg)

        reached_warnsize = bool(warnsize and expected_size > warnsize)
        if reached_warnsize:
            logger.warning(
                get_warnsize_msg(expected_size, warnsize, request, expected=True)
            )

        d: Deferred[_ResultT] = Deferred(partial(self._cancel, txresponse=txresponse))
        txresponse.deliverBody(
            _ResponseReader(
                finished=d,
                txresponse=txresponse,
                request=request,
                bodybuf=bodybuf,
                maxsize=maxsize,
                warnsize=warnsize,
                reached_warnsize=reached_warnsize,
                fail_on_dataloss=fail_on_dataloss,
                crawler=self._crawler,
                tls_verbose_logging=self._tls_verbose_logging,
            )
        )

        # save response for timeouts
        self._txresponse = txresponse

        return d

    @staticmethod
    def _cancel(_: Any, txresponse: TxResponse) -> None:
        # Abort connection immediately.
        txresponse._transport._producer.abortConnection()

    def _cb_bodydone(
        self,
        result: _ResultT,
        url: str,
        body_file: str | os.PathLike[str] | None,
    ) -> Response:
        headers = self._headers_from_twisted_response(result["txresponse"])
        version = result["txresponse"].version
        protocol = f"{version[0].decode()}/{version[1]}.{version[2]}"
        return make_response(
            url=url,
            status=int(result["txresponse"].code),
            headers=headers,
            body=result.get("body", b""),
            flags=result.get("flags"),
            certificate=result.get("certificate"),
            ip_address=result.get("ip_address"),
            protocol=protocol,
            stop_download=result.get("stop_download"),
            body_file=body_file,
        )


@implementer(IBodyProducer)
class _RequestBodyProducer:
    def __init__(self, body: bytes):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer: IConsumer) -> Deferred[None]:
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self) -> None:
        pass

    def stopProducing(self) -> None:
        pass


class _ResponseReader(Protocol):
    def __init__(
        self,
        finished: Deferred[_ResultT],
        txresponse: TxResponse,
        request: Request,
        bodybuf: BinaryIO,
        maxsize: int,
        warnsize: int,
        fail_on_dataloss: bool,
        crawler: Crawler,
        *,
        reached_warnsize: bool = False,
        tls_verbose_logging: bool = False,
    ):
        self._finished: Deferred[_ResultT] = finished
        self._txresponse: TxResponse = txresponse
        self._request: Request = request
        self._bodybuf: BinaryIO = bodybuf
        self._maxsize: int = maxsize
        self._warnsize: int = warnsize
        self._fail_on_dataloss: bool = fail_on_dataloss
        self._reached_warnsize: bool = reached_warnsize
        self._bytes_received: int = 0
        self._certificate: ssl.Certificate | None = None
        self._ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
        self._crawler: Crawler = crawler
        self._tls_verbose_logging: bool = tls_verbose_logging

    def _finish_response(
        self, flags: list[str] | None = None, stop_download: StopDownload | None = None
    ) -> None:
        self._finished.callback(
            {
                "txresponse": self._txresponse,
                "body": (
                    self._bodybuf.getvalue()
                    if isinstance(self._bodybuf, BytesIO)
                    else b""
                ),
                "flags": flags,
                "certificate": self._certificate,
                "ip_address": self._ip_address,
                "stop_download": stop_download,
            }
        )

    def connectionMade(self) -> None:
        assert self.transport
        with suppress(AttributeError):
            self._certificate = ssl.Certificate(
                self.transport._producer.getPeerCertificate()
            )
        self._ip_address = ipaddress.ip_address(self.transport._producer.getPeer().host)

        if self._tls_verbose_logging:
            connection = self.transport._producer.getHandle()
            hostname = urlparse_cached(self._request).hostname
            assert hostname is not None
            _log_ssl_conn_debug_info(hostname, connection)

    def dataReceived(self, data: bytes) -> None:
        # This maybe called several times after cancel was called with buffered data.
        if self._finished.called:
            return

        assert self.transport
        self._bodybuf.write(data)
        self._bytes_received += len(data)

        if stop_download := check_stop_download(
            signals.bytes_received, self._crawler, self._request, data=data
        ):
            self.transport.stopProducing()
            self.transport.loseConnection()
            self._finish_response(stop_download=stop_download)

        if self._maxsize and self._bytes_received > self._maxsize:
            logger.warning(
                get_maxsize_msg(
                    self._bytes_received, self._maxsize, self._request, expected=False
                )
            )
            # Clear buffer earlier to avoid keeping data in memory for a long time.
            self._bodybuf.truncate(0)
            self._finished.cancel()

        if (
            self._warnsize
            and self._bytes_received > self._warnsize
            and not self._reached_warnsize
        ):
            self._reached_warnsize = True
            logger.warning(
                get_warnsize_msg(
                    self._bytes_received, self._warnsize, self._request, expected=False
                )
            )

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        if self._finished.called:
            return

        if reason.check(ResponseDone):
            self._finish_response()
            return

        if reason.check(PotentialDataLoss):
            self._finish_response(flags=["partial"])
            return

        # Twisted ends a response body in one of three ways: ResponseDone,
        # PotentialDataLoss, or a ResponseFailed wrapping _DataLoss. See
        # twisted.web._newclient.HTTPClientParser.connectionLost().
        assert reason.check(ResponseFailed)
        assert any(
            r.check(_DataLoss)
            for r in reason.value.reasons  # type: ignore[union-attr]
        )
        if not self._fail_on_dataloss:
            self._finish_response(flags=["dataloss"])
            return

        exc = ResponseDataLossError()
        exc.__cause__ = reason.value
        self._finished.errback(exc)
