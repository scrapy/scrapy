"""Download handlers for http and https schemes"""

from time import time
from cStringIO import StringIO
from urlparse import urldefrag

from zope.interface import implements
from twisted.internet import defer, reactor, protocol, ssl
from twisted.web.http_headers import Headers as TxHeaders
from twisted.web.iweb import IBodyProducer
from twisted.internet.error import TimeoutError, SSLError
from twisted.web.http import PotentialDataLoss
from scrapy.xlib.tx import Agent, ProxyAgent, ResponseDone, \
    HTTPConnectionPool, TCP4ClientEndpoint

from scrapy.http import Headers
from scrapy.responsetypes import responsetypes
from scrapy.core.downloader.webclient import _parse
from scrapy.utils.misc import load_object


class HTTP11DownloadHandler(object):

    def __init__(self, settings):
        self._pool = HTTPConnectionPool(reactor, persistent=True)
        self._pool.maxPersistentPerHost = settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')
        self._pool._factory.noisy = False
        self._contextFactoryClass = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])
        self._contextFactory = self._contextFactoryClass()

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        agent = ScrapyAgent(contextFactory=self._contextFactory, pool=self._pool)
        return agent.download_request(request)

    def close(self):
        return self._pool.closeCachedConnections()


class TunnelingTCP4ClientEndpoint(TCP4ClientEndpoint):
    """An endpoint that tunnels through proxies to allow HTTPS downloads. To
    accomplish that, this endpoint sends an HTTP CONNECT to the proxy. If the
    proxy fails to open the tunnel this endpoint will behave as a
    L{TCP4ClientEndpoint}.
    The HTTP CONNECT is always sent when using this endpoint, I think this could
    be improved as the CONNECT will be redundant if the connection associated
    with this endpoint comes from the pool and a CONNECT has already been issued
    for it.
    """

    def __init__(self, reactor, host, port, proxyHost, proxyPort,
                contextFactory, timeout=30, bindAddress=None):
        super(TunnelingTCP4ClientEndpoint, self).__init__(reactor, proxyHost,
            proxyPort, timeout, bindAddress)
        self._tunnelReadyDeferred = defer.Deferred()
        # Although we will connect to the proxy, we need the host and port of
        # the destination server in order to send the HTTP CONNECT.
        self._tunneledHost = host
        self._tunneledPort = port
        self._contextFactory = contextFactory

    def requestTunnel(self, protocol):
        """Asks the proxy to open a tunnel."""
        # Ask for the proxy to open the tunnel.
        protocol.transport.write('CONNECT %s:%s HTTP/1.1\n\n' %
                                 (self._tunneledHost, self._tunneledPort))
        # This hack is not so nice. Substitute the dataReceived method
        # temporarily to intercept the response from the proxy.
        self._protocolDataReceived = protocol.dataReceived
        protocol.dataReceived = self.processProxyResponse
        # Store the protocol because we will have to pass it when triggering the
        # deferred returned in the connect method.
        self._protocol = protocol
        return protocol

    def processProxyResponse(self, bytes):
        """Processes the response from the proxy. If the tunnel is successfully
        created, notifies the client that we are ready to send requests.
        """
        # Restore the protocol dataReceived method.
        self._protocol.dataReceived = self._protocolDataReceived
        if bytes.find('200 Connection established') > 0:
            # The tunnel is ready, switch transport to TLS.
            self._protocol.transport.startTLS(self._contextFactory,
                                              self._protocolFactory)
            # Trigger the callback with the protocol as the value.
            self._tunnelReadyDeferred.callback(self._protocol)
        else:
            # The proxy could not open the tunnel and will drop the connection;
            # (we need to check if this is common to every proxy). In order to
            # allow the client to send the request and get a response from the
            # proxy, we will intercept the connectionLost message and restore
            # the connection.
            self._protocolConnectionLost = self._protocol.connectionLost
            self._protocol.connectionLost = self.connectionLost

    def connectFailed(self, reason):
        """Propagates the errback to the appropriate deferred."""
        self._tunnelReadyDeferred.errback(reason)

    def connectionLost(self, reason):
        """Restores the connection to the proxy server but does not request
        for it to open a tunnel.
        """
        # Restore and call the protocol connection lost method.
        self._protocol.connectionLost = self._protocolConnectionLost
        self._protocol.connectionLost(reason)
        # Restore the connection to the proxy but don't open the tunnel.
        self.connect(self._protocolFactory, False)

    def connect(self, protocolFactory, openTunnel=True):
        # Store the protocol factory as we will need it to switch to TLS.
        self._protocolFactory = protocolFactory
        connectDeferred = super(TunnelingTCP4ClientEndpoint,
                                self).connect(protocolFactory)
        if openTunnel:
            # Add a callback to open the tunnel when the connection is ready.
            connectDeferred.addCallback(self.requestTunnel)
            connectDeferred.addErrback(self.connectFailed)
            # Return a deferred that will be triggered when the tunnel is ready.
            return self._tunnelReadyDeferred
        else:
            def cbCallback(protocol):
                self._tunnelReadyDeferred.callback(protocol)
            connectDeferred.addCallback(cbCallback)
            return connectDeferred


class TunnelingAgent(Agent):
    """An agent that uses a L{TunnelingTCP4ClientEndpoint} to make HTTPS
    downloads. It may look strange that we have chosen to subclass Agent and not
    ProxyAgent but consider that after the tunnel is opened the proxy is
    transparent to the client; thus the agent should behave like there is no
    proxy involved.
    """

    def __init__(self, reactor, proxyHost, proxyPort, contextFactory=None,
                 connectTimeout=None, bindAddress=None, pool=None):
        super(TunnelingAgent, self).__init__(reactor, contextFactory,
            connectTimeout, bindAddress, pool)
        self._proxyHost = proxyHost
        self._proxyPort = proxyPort

    def _getEndpoint(self, scheme, host, port):
        return TunnelingTCP4ClientEndpoint(self._reactor, host, port,
            self._proxyHost, self._proxyPort, self._contextFactory,
            self._connectTimeout, self._bindAddress)


class ScrapyAgent(object):

    _Agent = Agent
    _ProxyAgent = ProxyAgent
    _TunnelingAgent = TunnelingAgent

    def __init__(self, contextFactory=None, connectTimeout=10, bindAddress=None,
                 pool=None):
        self._contextFactory = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress
        self._pool = pool

    def _get_agent(self, request, timeout):
        bindaddress = request.meta.get('bindaddress') or self._bindAddress
        proxy = request.meta.get('proxy')
        if proxy:
            _, _, proxyHost, proxyPort, _ = _parse(proxy)
            scheme = _parse(request.url)[0]
            if  scheme == 'https':
                # We need to tunnel the proxy using an HTTP CONNECT.
                return self._TunnelingAgent(reactor, proxyHost, proxyPort,
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
