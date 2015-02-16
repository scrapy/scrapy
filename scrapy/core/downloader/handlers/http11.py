"""Download handlers for http and https schemes"""

import re

from time import time
from cStringIO import StringIO
from urlparse import urldefrag

from zope.interface import implements
from twisted.internet import defer, reactor, protocol
from twisted.web.http_headers import Headers as TxHeaders
from twisted.web.iweb import IBodyProducer
from twisted.internet.error import TimeoutError
from twisted.web.http import PotentialDataLoss
from scrapy.xlib.tx import Agent, ProxyAgent, ResponseDone, \
    HTTPConnectionPool, TCP4ClientEndpoint

from scrapy.http import Headers
from scrapy.responsetypes import responsetypes
from scrapy.core.downloader.webclient import _parse
from scrapy.utils.misc import load_object
from scrapy import twisted_version


class HTTP11DownloadHandler(object):

    def __init__(self, settings):
        self._pool = HTTPConnectionPool(reactor, persistent=True)
        self._pool.maxPersistentPerHost = settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')
        self._pool._factory.noisy = False
        self._contextFactoryClass = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])
        self._contextFactory = self._contextFactoryClass()
        self._disconnect_timeout = 1

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        agent = ScrapyAgent(contextFactory=self._contextFactory, pool=self._pool)
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

    _responseMatcher = re.compile('HTTP/1\.. 200')

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
        tunnelReq = 'CONNECT %s:%s HTTP/1.1\r\n' % (self._tunneledHost,
                                                  self._tunneledPort)
        if self._proxyAuthHeader:
            tunnelReq += 'Proxy-Authorization: %s\r\n' % self._proxyAuthHeader
        tunnelReq += '\r\n'
        protocol.transport.write(tunnelReq)
        self._protocolDataReceived = protocol.dataReceived
        protocol.dataReceived = self.processProxyResponse
        self._protocol = protocol
        return protocol

    def processProxyResponse(self, bytes):
        """Processes the response from the proxy. If the tunnel is successfully
        created, notifies the client that we are ready to send requests. If not
        raises a TunnelError.
        """
        self._protocol.dataReceived = self._protocolDataReceived
        if  TunnelingTCP4ClientEndpoint._responseMatcher.match(bytes):
            self._protocol.transport.startTLS(self._contextFactory,
                                              self._protocolFactory)
            self._tunnelReadyDeferred.callback(self._protocol)
        else:
            self._tunnelReadyDeferred.errback(
                TunnelError('Could not open CONNECT tunnel.'))

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



class ScrapyAgent(object):

    _Agent = Agent
    _ProxyAgent = ProxyAgent
    _TunnelingAgent = TunnelingAgent

    def __init__(self, contextFactory=None, connectTimeout=10, bindAddress=None, pool=None):
        self._contextFactory = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress
        self._pool = pool

    def _get_agent(self, request, timeout):
        bindaddress = request.meta.get('bindaddress') or self._bindAddress
        proxy = request.meta.get('proxy')
        if proxy:
            _, _, proxyHost, proxyPort, proxyParams = _parse(proxy)
            scheme = _parse(request.url)[0]
            omitConnectTunnel = proxyParams.find('noconnect') >= 0
            if  scheme == 'https' and not omitConnectTunnel:
                proxyConf = (proxyHost, proxyPort,
                             request.headers.get('Proxy-Authorization', None))
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
        method = request.method
        headers = TxHeaders(request.headers)
        if isinstance(agent, self._TunnelingAgent):
            headers.removeHeader('Proxy-Authorization')
        bodyproducer = _RequestBodyProducer(request.body) if request.body else None

        start_time = time()
        d = agent.request(method, url, headers, bodyproducer)
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
        raise TimeoutError("Getting %s took longer than %s seconds." % (url, timeout))

    def _cb_latency(self, result, request, start_time):
        request.meta['download_latency'] = time() - start_time
        return result

    def _cb_bodyready(self, txresponse, request):
        # deliverBody hangs for responses without body
        if txresponse.length == 0:
            return txresponse, '', None

        def _cancel(_):
            txresponse._transport._producer.loseConnection()

        d = defer.Deferred(_cancel)
        txresponse.deliverBody(_ResponseReader(d, txresponse, request))
        return d

    def _cb_bodydone(self, result, request, url):
        txresponse, body, flags = result
        status = int(txresponse.code)
        headers = Headers(txresponse.headers.getAllRawHeaders())
        respcls = responsetypes.from_args(headers=headers, url=url)
        return respcls(url=url, status=status, headers=headers, body=body, flags=flags)


class _RequestBodyProducer(object):
    implements(IBodyProducer)

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

    def __init__(self, finished, txresponse, request):
        self._finished = finished
        self._txresponse = txresponse
        self._request = request
        self._bodybuf = StringIO()

    def dataReceived(self, bodyBytes):
        self._bodybuf.write(bodyBytes)

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
