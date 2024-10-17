"""Download handlers for http and https schemes"""

from __future__ import annotations

import ipaddress
import logging
import re
from contextlib import suppress
from io import BytesIO
from time import time
from typing import TYPE_CHECKING, Any, TypedDict, TypeVar
from urllib.parse import urldefrag, urlunparse

from twisted.internet import ssl
from twisted.internet.defer import CancelledError, Deferred, succeed
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.error import TimeoutError
from twisted.internet.protocol import Factory, Protocol, connectionDone
from twisted.python.failure import Failure
from twisted.web.client import URI, Agent, HTTPConnectionPool
from twisted.web.client import Response as TxResponse
from twisted.web.client import ResponseDone, ResponseFailed
from twisted.web.http import PotentialDataLoss, _DataLoss
from twisted.web.http_headers import Headers as TxHeaders
from twisted.web.iweb import UNKNOWN_LENGTH, IBodyProducer, IPolicyForHTTPS
from zope.interface import implementer

from scrapy import Request, Spider, signals
from scrapy.core.downloader.contextfactory import load_context_factory_from_settings
from scrapy.core.downloader.webclient import _parse
from scrapy.exceptions import StopDownload
from scrapy.http import Headers, Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    from twisted.internet.base import ReactorBase
    from twisted.internet.interfaces import IConsumer

    # typing.NotRequired and typing.Self require Python 3.11
    from typing_extensions import NotRequired, Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class _ResultT(TypedDict):
    txresponse: TxResponse
    body: bytes
    flags: list[str] | None
    certificate: ssl.Certificate | None
    ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    failure: NotRequired[Failure | None]


class HTTP11DownloadHandler:
    lazy = False

    def __init__(self, settings: BaseSettings, crawler: Crawler):
        self._crawler = crawler

        from twisted.internet import reactor

        self._pool: HTTPConnectionPool = HTTPConnectionPool(reactor, persistent=True)
        self._pool.maxPersistentPerHost = settings.getint(
            "CONCURRENT_REQUESTS_PER_DOMAIN"
        )
        self._pool._factory.noisy = False

        self._contextFactory: IPolicyForHTTPS = load_context_factory_from_settings(
            settings, crawler
        )
        self._default_maxsize: int = settings.getint("DOWNLOAD_MAXSIZE")
        self._default_warnsize: int = settings.getint("DOWNLOAD_WARNSIZE")
        self._fail_on_dataloss: bool = settings.getbool("DOWNLOAD_FAIL_ON_DATALOSS")
        self._disconnect_timeout: int = 1

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        """Return a deferred for the HTTP download"""
        agent = ScrapyAgent(
            contextFactory=self._contextFactory,
            pool=self._pool,
            maxsize=getattr(spider, "download_maxsize", self._default_maxsize),
            warnsize=getattr(spider, "download_warnsize", self._default_warnsize),
            fail_on_dataloss=self._fail_on_dataloss,
            crawler=self._crawler,
        )
        return agent.download_request(request)

    def close(self) -> Deferred[None]:
        from twisted.internet import reactor

        d: Deferred[None] = self._pool.closeCachedConnections()
        # closeCachedConnections will hang on network or server issues, so
        # we'll manually timeout the deferred.
        #
        # Twisted issue addressing this problem can be found here:
        # https://twistedmatrix.com/trac/ticket/7738.
        #
        # closeCachedConnections doesn't handle external errbacks, so we'll
        # issue a callback after `_disconnect_timeout` seconds.
        delayed_call = reactor.callLater(self._disconnect_timeout, d.callback, [])

        def cancel_delayed_call(result: _T) -> _T:
            if delayed_call.active():
                delayed_call.cancel()
            return result

        d.addBoth(cancel_delayed_call)
        return d


class TunnelError(Exception):
    """An HTTP CONNECT tunnel could not be established by the proxy."""


class TunnelingTCP4ClientEndpoint(TCP4ClientEndpoint):
    """An endpoint that tunnels through proxies to allow HTTPS downloads. To
    accomplish that, this endpoint sends an HTTP CONNECT to the proxy.
    The HTTP CONNECT is always sent when using this endpoint, I think this could
    be improved as the CONNECT will be redundant if the connection associated
    with this endpoint comes from the pool and a CONNECT has already been issued
    for it.
    """

    _truncatedLength = 1000
    _responseAnswer = (
        r"HTTP/1\.. (?P<status>\d{3})(?P<reason>.{," + str(_truncatedLength) + r"})"
    )
    _responseMatcher = re.compile(_responseAnswer.encode())

    def __init__(
        self,
        reactor: ReactorBase,
        host: str,
        port: int,
        proxyConf: tuple[str, int, bytes | None],
        contextFactory: IPolicyForHTTPS,
        timeout: float = 30,
        bindAddress: tuple[str, int] | None = None,
    ):
        proxyHost, proxyPort, self._proxyAuthHeader = proxyConf
        super().__init__(reactor, proxyHost, proxyPort, timeout, bindAddress)
        self._tunnelReadyDeferred: Deferred[Protocol] = Deferred()
        self._tunneledHost: str = host
        self._tunneledPort: int = port
        self._contextFactory: IPolicyForHTTPS = contextFactory
        self._connectBuffer: bytearray = bytearray()

    def requestTunnel(self, protocol: Protocol) -> Protocol:
        """Asks the proxy to open a tunnel."""
        assert protocol.transport
        tunnelReq = tunnel_request_data(
            self._tunneledHost, self._tunneledPort, self._proxyAuthHeader
        )
        protocol.transport.write(tunnelReq)
        self._protocolDataReceived = protocol.dataReceived
        protocol.dataReceived = self.processProxyResponse  # type: ignore[method-assign]
        self._protocol = protocol
        return protocol

    def processProxyResponse(self, data: bytes) -> None:
        """Processes the response from the proxy. If the tunnel is successfully
        created, notifies the client that we are ready to send requests. If not
        raises a TunnelError.
        """
        assert self._protocol.transport
        self._connectBuffer += data
        # make sure that enough (all) bytes are consumed
        # and that we've got all HTTP headers (ending with a blank line)
        # from the proxy so that we don't send those bytes to the TLS layer
        #
        # see https://github.com/scrapy/scrapy/issues/2491
        if b"\r\n\r\n" not in self._connectBuffer:
            return
        self._protocol.dataReceived = self._protocolDataReceived  # type: ignore[method-assign]
        respm = TunnelingTCP4ClientEndpoint._responseMatcher.match(self._connectBuffer)
        if respm and int(respm.group("status")) == 200:
            # set proper Server Name Indication extension
            sslOptions = self._contextFactory.creatorForNetloc(  # type: ignore[call-arg,misc]
                self._tunneledHost, self._tunneledPort
            )
            self._protocol.transport.startTLS(sslOptions, self._protocolFactory)
            self._tunnelReadyDeferred.callback(self._protocol)
        else:
            extra: Any
            if respm:
                extra = {
                    "status": int(respm.group("status")),
                    "reason": respm.group("reason").strip(),
                }
            else:
                extra = data[: self._truncatedLength]
            self._tunnelReadyDeferred.errback(
                TunnelError(
                    "Could not open CONNECT tunnel with proxy "
                    f"{self._host}:{self._port} [{extra!r}]"
                )
            )

    def connectFailed(self, reason: Failure) -> None:
        """Propagates the errback to the appropriate deferred."""
        self._tunnelReadyDeferred.errback(reason)

    def connect(self, protocolFactory: Factory) -> Deferred[Protocol]:
        self._protocolFactory = protocolFactory
        connectDeferred = super().connect(protocolFactory)
        connectDeferred.addCallback(self.requestTunnel)
        connectDeferred.addErrback(self.connectFailed)
        return self._tunnelReadyDeferred


def tunnel_request_data(
    host: str, port: int, proxy_auth_header: bytes | None = None
) -> bytes:
    r"""
    Return binary content of a CONNECT request.

    >>> from scrapy.utils.python import to_unicode as s
    >>> s(tunnel_request_data("example.com", 8080))
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\n\r\n'
    >>> s(tunnel_request_data("example.com", 8080, b"123"))
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\nProxy-Authorization: 123\r\n\r\n'
    >>> s(tunnel_request_data(b"example.com", "8090"))
    'CONNECT example.com:8090 HTTP/1.1\r\nHost: example.com:8090\r\n\r\n'
    """
    host_value = to_bytes(host, encoding="ascii") + b":" + to_bytes(str(port))
    tunnel_req = b"CONNECT " + host_value + b" HTTP/1.1\r\n"
    tunnel_req += b"Host: " + host_value + b"\r\n"
    if proxy_auth_header:
        tunnel_req += b"Proxy-Authorization: " + proxy_auth_header + b"\r\n"
    tunnel_req += b"\r\n"
    return tunnel_req


class TunnelingAgent(Agent):
    """An agent that uses a L{TunnelingTCP4ClientEndpoint} to make HTTPS
    downloads. It may look strange that we have chosen to subclass Agent and not
    ProxyAgent but consider that after the tunnel is opened the proxy is
    transparent to the client; thus the agent should behave like there is no
    proxy involved.
    """

    def __init__(
        self,
        *,
        reactor: ReactorBase,
        proxyConf: tuple[str, int, bytes | None],
        contextFactory: IPolicyForHTTPS,
        connectTimeout: float | None = None,
        bindAddress: bytes | None = None,
        pool: HTTPConnectionPool | None = None,
    ):
        super().__init__(reactor, contextFactory, connectTimeout, bindAddress, pool)
        self._proxyConf: tuple[str, int, bytes | None] = proxyConf
        self._contextFactory: IPolicyForHTTPS = contextFactory

    def _getEndpoint(self, uri: URI) -> TunnelingTCP4ClientEndpoint:
        return TunnelingTCP4ClientEndpoint(
            reactor=self._reactor,
            host=uri.host,
            port=uri.port,
            proxyConf=self._proxyConf,
            contextFactory=self._contextFactory,
            timeout=self._endpointFactory._connectTimeout,
            bindAddress=self._endpointFactory._bindAddress,
        )

    def _requestWithEndpoint(
        self,
        key: Any,
        endpoint: TCP4ClientEndpoint,
        method: bytes,
        parsedURI: bytes,
        headers: TxHeaders | None,
        bodyProducer: IBodyProducer | None,
        requestPath: bytes,
    ) -> Deferred[TxResponse]:
        # proxy host and port are required for HTTP pool `key`
        # otherwise, same remote host connection request could reuse
        # a cached tunneled connection to a different proxy
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


class ScrapyProxyAgent(Agent):
    def __init__(
        self,
        reactor: ReactorBase,
        proxyURI: bytes,
        connectTimeout: float | None = None,
        bindAddress: bytes | None = None,
        pool: HTTPConnectionPool | None = None,
    ):
        super().__init__(
            reactor=reactor,
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
    ) -> Deferred[TxResponse]:
        """
        Issue a new request via the configured proxy.
        """
        # Cache *all* connections under the same key, since we are only
        # connecting to a single destination, the proxy:
        return self._requestWithEndpoint(
            key=("http-proxy", self._proxyURI.host, self._proxyURI.port),
            endpoint=self._getEndpoint(self._proxyURI),
            method=method,
            parsedURI=URI.fromBytes(uri),
            headers=headers,
            bodyProducer=bodyProducer,
            requestPath=uri,
        )


class ScrapyAgent:
    _Agent = Agent
    _ProxyAgent = ScrapyProxyAgent
    _TunnelingAgent = TunnelingAgent

    def __init__(
        self,
        *,
        contextFactory: IPolicyForHTTPS,
        connectTimeout: float = 10,
        bindAddress: bytes | None = None,
        pool: HTTPConnectionPool | None = None,
        maxsize: int = 0,
        warnsize: int = 0,
        fail_on_dataloss: bool = True,
        crawler: Crawler,
    ):
        self._contextFactory: IPolicyForHTTPS = contextFactory
        self._connectTimeout: float = connectTimeout
        self._bindAddress: bytes | None = bindAddress
        self._pool: HTTPConnectionPool | None = pool
        self._maxsize: int = maxsize
        self._warnsize: int = warnsize
        self._fail_on_dataloss: bool = fail_on_dataloss
        self._txresponse: TxResponse | None = None
        self._crawler: Crawler = crawler

    def _get_agent(self, request: Request, timeout: float) -> Agent:
        from twisted.internet import reactor

        bindaddress = request.meta.get("bindaddress") or self._bindAddress
        proxy = request.meta.get("proxy")
        if proxy:
            proxyScheme, proxyNetloc, proxyHost, proxyPort, proxyParams = _parse(proxy)
            scheme = _parse(request.url)[0]
            proxyHost_str = to_unicode(proxyHost)
            if scheme == b"https":
                proxyAuth = request.headers.get(b"Proxy-Authorization", None)
                proxyConf = (proxyHost_str, proxyPort, proxyAuth)
                return self._TunnelingAgent(
                    reactor=reactor,
                    proxyConf=proxyConf,
                    contextFactory=self._contextFactory,
                    connectTimeout=timeout,
                    bindAddress=bindaddress,
                    pool=self._pool,
                )
            proxyScheme = proxyScheme or b"http"
            proxyURI = urlunparse(
                (proxyScheme, proxyNetloc, proxyParams, b"", b"", b"")
            )
            return self._ProxyAgent(
                reactor=reactor,
                proxyURI=to_bytes(proxyURI, encoding="ascii"),
                connectTimeout=timeout,
                bindAddress=bindaddress,
                pool=self._pool,
            )

        return self._Agent(
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
        method = to_bytes(request.method)
        headers = TxHeaders(request.headers)
        if isinstance(agent, self._TunnelingAgent):
            headers.removeHeader(b"Proxy-Authorization")
        if request.body:
            bodyproducer = _RequestBodyProducer(request.body)
        else:
            bodyproducer = None
        start_time = time()
        d: Deferred[TxResponse] = agent.request(
            method, to_bytes(url, encoding="ascii"), headers, bodyproducer
        )
        # set download latency
        d.addCallback(self._cb_latency, request, start_time)
        # response body is ready to be consumed
        d2: Deferred[_ResultT] = d.addCallback(self._cb_bodyready, request)
        d3: Deferred[Response] = d2.addCallback(self._cb_bodydone, request, url)
        # check download timeout
        self._timeout_cl = reactor.callLater(timeout, d3.cancel)
        d3.addBoth(self._cb_timeout, request, url, timeout)
        return d3

    def _cb_timeout(self, result: _T, request: Request, url: str, timeout: float) -> _T:
        if self._timeout_cl.active():
            self._timeout_cl.cancel()
            return result
        # needed for HTTPS requests, otherwise _ResponseReader doesn't
        # receive connectionLost()
        if self._txresponse:
            self._txresponse._transport.stopProducing()

        raise TimeoutError(f"Getting {url} took longer than {timeout} seconds.")

    def _cb_latency(self, result: _T, request: Request, start_time: float) -> _T:
        request.meta["download_latency"] = time() - start_time
        return result

    @staticmethod
    def _headers_from_twisted_response(response: TxResponse) -> Headers:
        headers = Headers()
        if response.length != UNKNOWN_LENGTH:
            headers[b"Content-Length"] = str(response.length).encode()
        headers.update(response.headers.getAllRawHeaders())
        return headers

    def _cb_bodyready(
        self, txresponse: TxResponse, request: Request
    ) -> _ResultT | Deferred[_ResultT]:
        headers_received_result = self._crawler.signals.send_catch_log(
            signal=signals.headers_received,
            headers=self._headers_from_twisted_response(txresponse),
            body_length=txresponse.length,
            request=request,
            spider=self._crawler.spider,
        )
        for handler, result in headers_received_result:
            if isinstance(result, Failure) and isinstance(result.value, StopDownload):
                logger.debug(
                    "Download stopped for %(request)s from signal handler %(handler)s",
                    {"request": request, "handler": handler.__qualname__},
                )
                txresponse._transport.stopProducing()
                txresponse._transport.loseConnection()
                return {
                    "txresponse": txresponse,
                    "body": b"",
                    "flags": ["download_stopped"],
                    "certificate": None,
                    "ip_address": None,
                    "failure": result if result.value.fail else None,
                }

        # deliverBody hangs for responses without body
        if txresponse.length == 0:
            return {
                "txresponse": txresponse,
                "body": b"",
                "flags": None,
                "certificate": None,
                "ip_address": None,
            }

        maxsize = request.meta.get("download_maxsize", self._maxsize)
        warnsize = request.meta.get("download_warnsize", self._warnsize)
        expected_size = txresponse.length if txresponse.length != UNKNOWN_LENGTH else -1
        fail_on_dataloss = request.meta.get(
            "download_fail_on_dataloss", self._fail_on_dataloss
        )

        if maxsize and expected_size > maxsize:
            warning_msg = (
                "Cancelling download of %(url)s: expected response "
                "size (%(size)s) larger than download max size (%(maxsize)s)."
            )
            warning_args = {
                "url": request.url,
                "size": expected_size,
                "maxsize": maxsize,
            }

            logger.warning(warning_msg, warning_args)

            txresponse._transport.loseConnection()
            raise CancelledError(warning_msg % warning_args)

        if warnsize and expected_size > warnsize:
            logger.warning(
                "Expected response size (%(size)s) larger than "
                "download warn size (%(warnsize)s) in request %(request)s.",
                {"size": expected_size, "warnsize": warnsize, "request": request},
            )

        def _cancel(_: Any) -> None:
            # Abort connection immediately.
            txresponse._transport._producer.abortConnection()

        d: Deferred[_ResultT] = Deferred(_cancel)
        txresponse.deliverBody(
            _ResponseReader(
                finished=d,
                txresponse=txresponse,
                request=request,
                maxsize=maxsize,
                warnsize=warnsize,
                fail_on_dataloss=fail_on_dataloss,
                crawler=self._crawler,
            )
        )

        # save response for timeouts
        self._txresponse = txresponse

        return d

    def _cb_bodydone(
        self, result: _ResultT, request: Request, url: str
    ) -> Response | Failure:
        headers = self._headers_from_twisted_response(result["txresponse"])
        respcls = responsetypes.from_args(headers=headers, url=url, body=result["body"])
        try:
            version = result["txresponse"].version
            protocol = f"{to_unicode(version[0])}/{version[1]}.{version[2]}"
        except (AttributeError, TypeError, IndexError):
            protocol = None
        response = respcls(
            url=url,
            status=int(result["txresponse"].code),
            headers=headers,
            body=result["body"],
            flags=result["flags"],
            certificate=result["certificate"],
            ip_address=result["ip_address"],
            protocol=protocol,
        )
        if result.get("failure"):
            assert result["failure"]
            result["failure"].value.response = response
            return result["failure"]
        return response


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
        maxsize: int,
        warnsize: int,
        fail_on_dataloss: bool,
        crawler: Crawler,
    ):
        self._finished: Deferred[_ResultT] = finished
        self._txresponse: TxResponse = txresponse
        self._request: Request = request
        self._bodybuf: BytesIO = BytesIO()
        self._maxsize: int = maxsize
        self._warnsize: int = warnsize
        self._fail_on_dataloss: bool = fail_on_dataloss
        self._fail_on_dataloss_warned: bool = False
        self._reached_warnsize: bool = False
        self._bytes_received: int = 0
        self._certificate: ssl.Certificate | None = None
        self._ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
        self._crawler: Crawler = crawler

    def _finish_response(
        self, flags: list[str] | None = None, failure: Failure | None = None
    ) -> None:
        self._finished.callback(
            {
                "txresponse": self._txresponse,
                "body": self._bodybuf.getvalue(),
                "flags": flags,
                "certificate": self._certificate,
                "ip_address": self._ip_address,
                "failure": failure,
            }
        )

    def connectionMade(self) -> None:
        assert self.transport
        if self._certificate is None:
            with suppress(AttributeError):
                self._certificate = ssl.Certificate(
                    self.transport._producer.getPeerCertificate()
                )

        if self._ip_address is None:
            self._ip_address = ipaddress.ip_address(
                self.transport._producer.getPeer().host
            )

    def dataReceived(self, bodyBytes: bytes) -> None:
        # This maybe called several times after cancel was called with buffered data.
        if self._finished.called:
            return

        assert self.transport
        self._bodybuf.write(bodyBytes)
        self._bytes_received += len(bodyBytes)

        bytes_received_result = self._crawler.signals.send_catch_log(
            signal=signals.bytes_received,
            data=bodyBytes,
            request=self._request,
            spider=self._crawler.spider,
        )
        for handler, result in bytes_received_result:
            if isinstance(result, Failure) and isinstance(result.value, StopDownload):
                logger.debug(
                    "Download stopped for %(request)s from signal handler %(handler)s",
                    {"request": self._request, "handler": handler.__qualname__},
                )
                self.transport.stopProducing()
                self.transport.loseConnection()
                failure = result if result.value.fail else None
                self._finish_response(flags=["download_stopped"], failure=failure)

        if self._maxsize and self._bytes_received > self._maxsize:
            logger.warning(
                "Received (%(bytes)s) bytes larger than download "
                "max size (%(maxsize)s) in request %(request)s.",
                {
                    "bytes": self._bytes_received,
                    "maxsize": self._maxsize,
                    "request": self._request,
                },
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
                "Received more bytes than download "
                "warn size (%(warnsize)s) in request %(request)s.",
                {"warnsize": self._warnsize, "request": self._request},
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

        if reason.check(ResponseFailed) and any(
            r.check(_DataLoss) for r in reason.value.reasons
        ):
            if not self._fail_on_dataloss:
                self._finish_response(flags=["dataloss"])
                return

            if not self._fail_on_dataloss_warned:
                logger.warning(
                    "Got data loss in %s. If you want to process broken "
                    "responses set the setting DOWNLOAD_FAIL_ON_DATALOSS = False"
                    " -- This message won't be shown in further requests",
                    self._txresponse.request.absoluteURI.decode(),
                )
                self._fail_on_dataloss_warned = True

        self._finished.errback(reason)
