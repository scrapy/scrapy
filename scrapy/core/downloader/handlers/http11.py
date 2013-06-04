"""Download handlers for http and https schemes"""

from time import time
from cStringIO import StringIO
from urlparse import urldefrag

from zope.interface import implements
from twisted.internet import defer, reactor, protocol
from twisted.web.http_headers import Headers as TxHeaders
from twisted.web.http import PotentialDataLoss
from twisted.web.iweb import IBodyProducer
from twisted.internet.error import TimeoutError
from scrapy.xlib.tx import Agent, ProxyAgent, ResponseDone, \
        ResponseFailed, HTTPConnectionPool, TCP4ClientEndpoint

from scrapy.http import Headers
from scrapy.responsetypes import responsetypes
from scrapy.core.downloader.webclient import _parse
from scrapy.utils.misc import load_object
from scrapy import log



class HTTP11DownloadHandler(object):

    def __init__(self, settings):
        self._pool = HTTPConnectionPool(reactor, persistent=True)
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

    def download_request(self, request):
        timeout = request.meta.get('download_timeout') or self._connectTimeout
        url = urldefrag(request.url)[0]
        method = request.method
        headers = TxHeaders(request.headers)
        bodyproducer = _RequestBodyProducer(request.body) if request.body else None
        agent = self._get_agent(request, timeout)
        start_time = time()
        d = agent.request(method, url, headers, bodyproducer)
        d.addBoth(self._both_cb, request, start_time, url, timeout)
        d.addCallback(self._downloaded, request)
        self._timeout_cl = reactor.callLater(timeout, d.cancel)
        return d

    def _both_cb(self, result, request, start_time, url, timeout):
        request.meta['download_latency'] = time() - start_time
        if self._timeout_cl.active():
            self._timeout_cl.cancel()
            return result
        raise TimeoutError("Getting %s took longer than %s seconds." % (url, timeout))

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

    def _downloaded(self, txresponse, request):
        if txresponse.length == 0:
            return self._build_response(('', None), txresponse, request)
        finished = defer.Deferred()
        finished.addCallback(self._build_response, txresponse, request)
        txresponse.deliverBody(_ResponseReader(finished))
        return finished

    def _build_response(self, (body, flag), txresponse, request):
        if flag is not None:
            request.meta[flag] = True
        url = urldefrag(request.url)[0]
        status = int(txresponse.code)
        headers = Headers(txresponse.headers.getAllRawHeaders())
        respcls = responsetypes.from_args(headers=headers, url=url)
        return respcls(url=url, status=status, headers=headers, body=body)


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

    def __init__(self, finished):
        self._finished = finished
        self._bodybuf = StringIO()

    def dataReceived(self, bodyBytes):
        self._bodybuf.write(bodyBytes)

    def connectionLost(self, reason):
        body = self._bodybuf.getvalue()
        if reason.check(ResponseDone):
            self._finished.callback((body, None))
        elif reason.check(PotentialDataLoss, ResponseFailed):
            self._finished.callback((body, 'partial_download'))
        else:
            self._finished.errback(reason)
