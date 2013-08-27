"""Download handlers for http and https schemes"""

from time import time
from cStringIO import StringIO
from urlparse import urldefrag

from zope.interface import implements
from twisted.internet import defer, reactor, protocol
from twisted.web.http_headers import Headers as TxHeaders
from twisted.web.iweb import IBodyProducer
from twisted.internet.error import TimeoutError
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


class ScrapyAgent(object):

    _Agent = Agent
    _ProxyAgent = ProxyAgent

    def __init__(self, contextFactory=None, connectTimeout=10, bindAddress=None, pool=None):
        self._contextFactory = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress
        self._pool = pool

    def _get_agent(self, request, timeout):
        bindaddress = request.meta.get('bindaddress') or self._bindAddress
        proxy = request.meta.get('proxy')
        if proxy:
            scheme, _, host, port, _ = _parse(proxy)
            endpoint = TCP4ClientEndpoint(reactor, host, port, timeout=timeout,
                                          bindAddress=bindaddress)
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
