"""Download handlers for http and https schemes"""

from time import time
from cStringIO import StringIO
from urlparse import urldefrag

from zope.interface import implements
from twisted.internet import defer, reactor, protocol
from twisted.web.client import Agent, ProxyAgent, ResponseDone, ResponseFailed
from twisted.web.http_headers import Headers
from twisted.web.http import PotentialDataLoss
from twisted.web.iweb import IBodyProducer
from twisted.internet.endpoints import TCP4ClientEndpoint

from scrapy.http import Headers as ScrapyHeaders
from scrapy.responsetypes import responsetypes
from scrapy.core.downloader.webclient import _parse


class ScrapyAgent(object):

    def __init__(self, contextFactory=None, connectTimeout=180, bindAddress=None):
        self._contextFactory = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress

    def launchRequest(self, request):
        request_timeout = request.meta.get('download_timeout') or self._connectTimeout

        proxy = request.meta.get('proxy')
        if proxy is not None and proxy != '':
            scheme, _, host, port, _ = _parse(proxy)
            endpoint = TCP4ClientEndpoint(reactor,
                host, port,
                timeout=request_timeout,
                bindAddress=self._bindAddress)
            agent = ProxyAgent(endpoint)
        else:
            agent = Agent(reactor,
                contextFactory=self._contextFactory,
                connectTimeout=request_timeout,
                bindAddress=self._bindAddress)

        request._tw_start_time = time()
        return agent.request(
                request.method,
                urldefrag(request.url)[0],
                Headers(request.headers),
                _RequestBodyProducer(request.body or ''),
        )


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


class Http11DownloadHandler(object):

    def __init__(self):
        self.debug = False

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        agent = ScrapyAgent(reactor)
        d = agent.launchRequest(request)
        d.addBoth(self._download_latency, request, time())
        d.addCallback(self._agent_callback, request)
        d.addErrback(self._agent_errback, request)
        return d

    def _download_latency(self, any_, request, start_time):
        request.meta['download_latency'] = time() - start_time
        return any_

    def _agent_callback(self, txresponse, request):
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
        headers = ScrapyHeaders(txresponse.headers.getAllRawHeaders())
        respcls = responsetypes.from_args(headers=headers, url=url)
        return respcls(url=url, status=status, headers=headers, body=body)

    def _agent_errback(self, failure, request):
        #log.err(failure, 'HTTP11 failure: %s' % request)
        return failure
