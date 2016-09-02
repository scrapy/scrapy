"""Download handlers for http and https schemes"""

import re
import logging
from io import BytesIO
from time import time
import warnings
from six.moves.urllib.parse import urldefrag

from zope.interface import implementer
from twisted.internet import defer, reactor, protocol
from twisted.web.http_headers import Headers as TxHeaders
from twisted.web.iweb import IBodyProducer, UNKNOWN_LENGTH
from twisted.internet.error import TimeoutError
from twisted.web.http import PotentialDataLoss
from scrapy.xlib.tx import Agent, ProxyAgent, ResponseDone, \
    HTTPConnectionPool, TCP4ClientEndpoint

from scrapy.http import Headers
from scrapy.responsetypes import responsetypes
from scrapy.core.downloader.webclient import _parse
from scrapy.core.downloader.tls import openssl_methods
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_bytes, to_unicode
from scrapy import twisted_version

logger = logging.getLogger(__name__)


class HTTP11DownloadHandler(object):

    def __init__(self, settings):
        self._pool = HTTPConnectionPool(reactor, persistent=True)
        self._pool.maxPersistentPerHost = settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')
        self._pool._factory.noisy = False

        self._sslMethod = openssl_methods[settings.get('DOWNLOADER_CLIENT_TLS_METHOD')]
        self._contextFactoryClass = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])
        # try method-aware context factory
        try:
            self._contextFactory = self._contextFactoryClass(method=self._sslMethod)
        except TypeError:
            # use context factory defaults
            self._contextFactory = self._contextFactoryClass()
            msg = """
 '%s' does not accept `method` argument (type OpenSSL.SSL method,\
 e.g. OpenSSL.SSL.SSLv23_METHOD).\
 Please upgrade your context factory class to handle it or ignore it.""" % (
                settings['DOWNLOADER_CLIENTCONTEXTFACTORY'],)
            warnings.warn(msg)
        self._default_maxsize = settings.getint('DOWNLOAD_MAXSIZE')
        self._default_warnsize = settings.getint('DOWNLOAD_WARNSIZE')
        self._disconnect_timeout = 1

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        agent = ScrapyAgent(contextFactory=self._contextFactory, pool=self._pool,
            maxsize=getattr(spider, 'download_maxsize', self._default_maxsize),
            warnsize=getattr(spider, 'download_warnsize', self._default_warnsize))
        return agent.download_request(request)

    def close(self):
        d = self._pool.closeCachedConnections()
        # closeCachedConnections will hang on network or server issues, so
        # we'll manually timeout the deferred.
        #
        # Twisted issue addressing this problem can be found here:
        # https://twistedmatrix.com/trac/ticket/7738.
        #
        # closeCachedConnections doesn't handle external errbacks, so we'll
        # issue a callback after `_disconnect_timeout` seconds.
        delayed_call = reactor.callLater(self._disconnect_timeout, d.callback, [])

        def cancel_delayed_call(result):
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

    _responseMatcher = re.compile(b'HTTP/1\.. (?P<status>\d{3})(?P<reason>.{,32})')

    def __init__(self, reactor, host, port, proxyConf, contextFactory,
                 timeout=30, bindAddress=None):
        proxyHost, proxyPort, self._proxyAuthHeader = proxyConf
        super(TunnelingTCP4ClientEndpoint, self).__init__(reactor, proxyHost,
            proxyPort, timeout, bindAddress)
        self._tunnelReadyDeferred = defer.Deferred()
        self._tunneledHost = host
        self._tunneledPort = port
        self._contextFactory = contextFactory

    def requestTunnel(self, protocol):
        """Asks the proxy to open a tunnel."""
        tunnelReq = tunnel_request_data(self._tunneledHost, self._tunneledPort,
                                        self._proxyAuthHeader)
        protocol.transport.write(tunnelReq)
        self._protocolDataReceived = protocol.dataReceived
        protocol.dataReceived = self.processProxyResponse
        self._protocol = protocol
        return protocol

    def processProxyResponse(self, rcvd_bytes):
        """Processes the response from the proxy. If the tunnel is successfully
        created, notifies the client that we are ready to send requests. If not
        raises a TunnelError.
        """
        self._protocol.dataReceived = self._protocolDataReceived
        respm = TunnelingTCP4ClientEndpoint._responseMatcher.match(rcvd_bytes)
        if respm and int(respm.group('status')) == 200:
            try:
                # this sets proper Server Name Indication extension
                # but is only available for Twisted>=14.0
                sslOptions = self._contextFactory.creatorForNetloc(
                    self._tunneledHost, self._tunneledPort)
            except AttributeError:
                # fall back to non-SNI SSL context factory
                sslOptions = self._contextFactory
            self._protocol.transport.startTLS(sslOptions,
                                              self._protocolFactory)
            self._tunnelReadyDeferred.callback(self._protocol)
        else:
            if respm:
                extra = {'status': int(respm.group('status')),
                         'reason': respm.group('reason').strip()}
            else:
                extra = rcvd_bytes[:32]
            self._tunnelReadyDeferred.errback(
                TunnelError('Could not open CONNECT tunnel with proxy %s:%s [%r]' % (
                    self._host, self._port, extra)))

    def connectFailed(self, reason):
        """Propagates the errback to the appropriate deferred."""
        self._tunnelReadyDeferred.errback(reason)

    def connect(self, protocolFactory):
        self._protocolFactory = protocolFactory
        connectDeferred = super(TunnelingTCP4ClientEndpoint,
                                self).connect(protocolFactory)
        connectDeferred.addCallback(self.requestTunnel)
        connectDeferred.addErrback(self.connectFailed)
        return self._tunnelReadyDeferred


def tunnel_request_data(host, port, proxy_auth_header=None):
    r"""
    Return binary content of a CONNECT request.

    >>> from scrapy.utils.python import to_native_str as s
    >>> s(tunnel_request_data("example.com", 8080))
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\n\r\n'
    >>> s(tunnel_request_data("example.com", 8080, b"123"))
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\nProxy-Authorization: 123\r\n\r\n'
    >>> s(tunnel_request_data(b"example.com", "8090"))
    'CONNECT example.com:8090 HTTP/1.1\r\nHost: example.com:8090\r\n\r\n'
    """
    host_value = to_bytes(host, encoding='ascii') + b':' + to_bytes(str(port))
    tunnel_req = b'CONNECT ' + host_value + b' HTTP/1.1\r\n'
    tunnel_req += b'Host: ' + host_value + b'\r\n'
    if proxy_auth_header:
        tunnel_req += b'Proxy-Authorization: ' + proxy_auth_header + b'\r\n'
    tunnel_req += b'\r\n'
    return tunnel_req


class TunnelingAgent(Agent):
    """An agent that uses a L{TunnelingTCP4ClientEndpoint} to make HTTPS
    downloads. It may look strange that we have chosen to subclass Agent and not
    ProxyAgent but consider that after the tunnel is opened the proxy is
    transparent to the client; thus the agent should behave like there is no
    proxy involved.
    """

    def __init__(self, reactor, proxyConf, contextFactory=None,
                 connectTimeout=None, bindAddress=None, pool=None):
        super(TunnelingAgent, self).__init__(reactor, contextFactory,
            connectTimeout, bindAddress, pool)
        self._proxyConf = proxyConf
        self._contextFactory = contextFactory

    if twisted_version >= (15, 0, 0):
        def _getEndpoint(self, uri):
            return TunnelingTCP4ClientEndpoint(
                self._reactor, uri.host, uri.port, self._proxyConf,
                self._contextFactory, self._endpointFactory._connectTimeout,
                self._endpointFactory._bindAddress)
    else:
        def _getEndpoint(self, scheme, host, port):
            return TunnelingTCP4ClientEndpoint(
                self._reactor, host, port, self._proxyConf,
                self._contextFactory, self._connectTimeout,
                self._bindAddress)

    def _requestWithEndpoint(self, key, endpoint, method, parsedURI,
            headers, bodyProducer, requestPath):
        # proxy host and port are required for HTTP pool `key`
        # otherwise, same remote host connection request could reuse
        # a cached tunneled connection to a different proxy
        key = key + self._proxyConf
        return super(TunnelingAgent, self)._requestWithEndpoint(key, endpoint, method, parsedURI,
            headers, bodyProducer, requestPath)


class ScrapyAgent(object):

    _Agent = Agent
    _ProxyAgent = ProxyAgent
    _TunnelingAgent = TunnelingAgent

    def __init__(self, contextFactory=None, connectTimeout=10, bindAddress=None, pool=None,
                 maxsize=0, warnsize=0):
        self._contextFactory = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress
        self._pool = pool
        self._maxsize = maxsize
        self._warnsize = warnsize
        self._txresponse = None

    def _get_agent(self, request, timeout):
        bindaddress = request.meta.get('bindaddress') or self._bindAddress
        proxy = request.meta.get('proxy')
        if proxy:
            _, _, proxyHost, proxyPort, proxyParams = _parse(proxy)
            scheme = _parse(request.url)[0]
            proxyHost = to_unicode(proxyHost)
            omitConnectTunnel = b'noconnect' in proxyParams
            if  scheme == b'https' and not omitConnectTunnel:
                proxyConf = (proxyHost, proxyPort,
                             request.headers.get(b'Proxy-Authorization', None))
                return self._TunnelingAgent(reactor, proxyConf,
                    contextFactory=self._contextFactory, connectTimeout=timeout,
                    bindAddress=bindaddress, pool=self._pool)
            else:
                endpoint = TCP4ClientEndpoint(reactor, proxyHost, proxyPort,
                    timeout=timeout, bindAddress=bindaddress)
                return self._ProxyAgent(endpoint)

        return self._Agent(reactor, contextFactory=self._contextFactory,
            connectTimeout=timeout, bindAddress=bindaddress, pool=self._pool)

    def download_request(self, request):
        timeout = request.meta.get('download_timeout') or self._connectTimeout
        agent = self._get_agent(request, timeout)

        # request details
        url = urldefrag(request.url)[0]
        method = to_bytes(request.method)
        headers = TxHeaders(request.headers)
        if isinstance(agent, self._TunnelingAgent):
            headers.removeHeader(b'Proxy-Authorization')
        if request.body:
            bodyproducer = _RequestBodyProducer(request.body)
        else:
            bodyproducer = None
            # Setting Content-Length: 0 even for POST requests is not a
            # MUST per HTTP RFCs, but it's common behavior, and some
            # servers require this, otherwise returning HTTP 411 Length required
            #
            # RFC 7230#section-3.3.2:
            # "a Content-Length header field is normally sent in a POST
            # request even when the value is 0 (indicating an empty payload body)."
            #
            # Twisted Agent will not add "Content-Length: 0" by itself
            if method == b'POST':
                headers.addRawHeader(b'Content-Length', b'0')

        start_time = time()
        d = agent.request(
            method, to_bytes(url, encoding='ascii'), headers, bodyproducer)
        # set download latency
        d.addCallback(self._cb_latency, request, start_time)
        # response body is ready to be consumed
        d.addCallback(self._cb_bodyready, request)
        d.addCallback(self._cb_bodydone, request, url)
        # check download timeout
        self._timeout_cl = reactor.callLater(timeout, d.cancel)
        d.addBoth(self._cb_timeout, request, url, timeout)
        return d

    def _cb_timeout(self, result, request, url, timeout):
        if self._timeout_cl.active():
            self._timeout_cl.cancel()
            return result
        # needed for HTTPS requests, otherwise _ResponseReader doesn't
        # receive connectionLost()
        if self._txresponse:
            self._txresponse._transport.stopProducing()

        raise TimeoutError("Getting %s took longer than %s seconds." % (url, timeout))

    def _cb_latency(self, result, request, start_time):
        request.meta['download_latency'] = time() - start_time
        return result

    def _cb_bodyready(self, txresponse, request):
        # deliverBody hangs for responses without body
        if txresponse.length == 0:
            return txresponse, b'', None

        maxsize = request.meta.get('download_maxsize', self._maxsize)
        warnsize = request.meta.get('download_warnsize', self._warnsize)
        expected_size = txresponse.length if txresponse.length != UNKNOWN_LENGTH else -1

        if maxsize and expected_size > maxsize:
            error_message = ("Cancelling download of {url}: expected response "
                             "size ({size}) larger than "
                             "download max size ({maxsize})."
            ).format(url=request.url, size=expected_size, maxsize=maxsize)

            logger.error(error_message)
            txresponse._transport._producer.loseConnection()
            raise defer.CancelledError(error_message)

        if warnsize and expected_size > warnsize:
            logger.warning("Expected response size (%(size)s) larger than "
                           "download warn size (%(warnsize)s).",
                           {'size': expected_size, 'warnsize': warnsize})

        def _cancel(_):
            txresponse._transport._producer.loseConnection()

        d = defer.Deferred(_cancel)
        txresponse.deliverBody(_ResponseReader(d, txresponse, request, maxsize, warnsize))

        # save response for timeouts
        self._txresponse = txresponse

        return d

    def _cb_bodydone(self, result, request, url):
        txresponse, body, flags = result
        status = int(txresponse.code)
        headers = Headers(txresponse.headers.getAllRawHeaders())
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)
        return respcls(url=url, status=status, headers=headers, body=body, flags=flags)


@implementer(IBodyProducer)
class _RequestBodyProducer(object):

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


class _ResponseReader(protocol.Protocol):

    def __init__(self, finished, txresponse, request, maxsize, warnsize):
        self._finished = finished
        self._txresponse = txresponse
        self._request = request
        self._bodybuf = BytesIO()
        self._maxsize  = maxsize
        self._warnsize  = warnsize
        self._reached_warnsize = False
        self._bytes_received = 0

    def dataReceived(self, bodyBytes):
        self._bodybuf.write(bodyBytes)
        self._bytes_received += len(bodyBytes)

        if self._maxsize and self._bytes_received > self._maxsize:
            logger.error("Received (%(bytes)s) bytes larger than download "
                         "max size (%(maxsize)s).",
                         {'bytes': self._bytes_received,
                          'maxsize': self._maxsize})
            self._finished.cancel()

        if self._warnsize and self._bytes_received > self._warnsize and not self._reached_warnsize:
            self._reached_warnsize = True
            logger.warning("Received more bytes than download "
                           "warn size (%(warnsize)s) in request %(request)s.",
                           {'warnsize': self._warnsize,
                            'request': self._request})

    def connectionLost(self, reason):
        if self._finished.called:
            return

        body = self._bodybuf.getvalue()
        if reason.check(ResponseDone):
            self._finished.callback((self._txresponse, body, None))
        elif reason.check(PotentialDataLoss):
            self._finished.callback((self._txresponse, body, ['partial']))
        else:
            self._finished.errback(reason)
