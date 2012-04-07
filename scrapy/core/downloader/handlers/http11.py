"""Download handlers for http and https schemes"""

from twisted.internet import reactor

from scrapy.exceptions import NotSupported
from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy.utils.httpobj import urlparse_cached
from scrapy import optional_features

from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy.http import Headers as ScrapyHeaders
from scrapy.utils.httpobj import urlparse_cached
from scrapy.responsetypes import responsetypes


from twisted.internet import defer, reactor, protocol
from twisted.web.client import Agent, ProxyAgent, ResponseDone, WebClientContextFactory

from twisted.web.http_headers import Headers
from twisted.web._newclient import Response

from twisted.web.http import PotentialDataLoss
from twisted.web._newclient import ResponseFailed
from twisted.web.iweb import IBodyProducer
from twisted.internet.error import TimeoutError

from twisted.internet.endpoints import TCP4ClientEndpoint

from time import time
from urlparse import urldefrag

from zope.interface import implements

from urlparse import urlparse, urlunparse, urldefrag

def _parsed_url_args(parsed):
    path = urlunparse(('', '', parsed.path or '/', parsed.params, parsed.query, ''))
    host = parsed.hostname
    port = parsed.port
    scheme = parsed.scheme
    netloc = parsed.netloc
    if port is None:
        port = 443 if scheme == 'https' else 80
    return scheme, netloc, host, port, path

def _parse(url):
    url = url.strip()
    parsed = urlparse(url)
    return _parsed_url_args(parsed)


class ScrapyAgent(object):
    def __init__(self, reactor, contextFactory=WebClientContextFactory(),
                 connectTimeout=180, bindAddress=None):
        self._reactor = reactor
        self._agent = Agent(self._reactor,
            contextFactory=contextFactory,
            connectTimeout=connectTimeout,
            bindAddress=bindAddress)

    def bindRequest(self, request):
        self._scrapyrequest = request

        proxy = self._scrapyrequest.meta.get('proxy')
        if proxy is not None and proxy != '':
            scheme, _, host, port, _ = _parse(proxy)
            endpoint = TCP4ClientEndpoint(self._reactor, host, port)
            self._agent = ProxyAgent(endpoint)
            self._agent._proxyEndpoint._timeout = request.meta.get('download_timeout') or self._agent._proxyEndpoint._timeout
        else:
            self._agent._connectTimeout = request.meta.get('download_timeout') or self._agent._connectTimeout

    def launch(self):
        self._scrapyrequest._tw_start_time = time()
        d = self._agent.request(
                self._scrapyrequest.method,
                urldefrag(self._scrapyrequest.url)[0],
                Headers(self._scrapyrequest.headers),
                ScrapyAgentRequestBodyProducer(self._scrapyrequest.body) if (self._scrapyrequest.body is not None) else None)
        return d


class ScrapyAgentRequestBodyProducer(object):
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


from cStringIO import StringIO
class ScrapyAgentResponseBodyReader(protocol.Protocol):

    def __init__(self, finished, response, scrapyRequest, debug=0):

        # finished is the deferred that will be fired
        self._finished = finished

        self.debug = debug

        self.status = int(response.code)
        self.resp_headers = list(response.headers.getAllRawHeaders())

        self._scrapyrequest = scrapyRequest
        self._scrapyrequest._tw_headers_time = time()
        self._scrapyrequest.meta['download_latency'] = self._scrapyrequest._tw_headers_time - self._scrapyrequest._tw_start_time

        # body
        self.bodyBuffer = StringIO()

    def dataReceived(self, bodyBytes):
        if self.debug > 2:
            print "dataReceived", len(bodyBytes), [bodyBytes[0:min(len(bodyBytes), 16)]]
        self.bodyBuffer.write(bodyBytes)

    def connectionLost(self, reason):

        if reason.check(PotentialDataLoss):
            if self.debug > 2:
                print "PotentialDataLoss"

        elif reason.check(ResponseFailed):
            if self.debug > 2:
                print "ResponseFailed"
                print reason.getErrorMessage()
                reason.getBriefTraceback()

        elif reason.check(ResponseDone):
            if self.debug > 2:
                print "ReponseDone"
                print "connection lost: %s" % reason
                print 'Finished receiving body:', reason.getErrorMessage()

        # fire the deferred with Scrapy Response object
        self._finished.callback(self._build_response())


    def _build_response(self):
        headers = ScrapyHeaders(self.resp_headers)
        respcls = responsetypes.from_args(headers=headers, url=urldefrag(self._scrapyrequest.url)[0])
        return respcls(
            url=urldefrag(self._scrapyrequest.url)[0],
            status=self.status,
            headers=headers,
            body=self.bodyBuffer.getvalue())


class HttpDownloadHandler(object):

    def __init__(self, httpclientfactory=None):
        self.debug = False


    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""

        agent = ScrapyAgent(reactor)
        agent.bindRequest(request)

        d = agent.launch()
        d.addCallback(self._agent_callback, request)
        d.addErrback(self._agent_errback, request)

        return d


    def _agent_callback(self, response, request):
        finished = defer.Deferred()
        reader = ScrapyAgentResponseBodyReader(finished, response, request, debug = 0)
        response.deliverBody(reader)

        if request.method != 'HEAD':
            return finished
        else:
            return reader._build_response()


    def _agent_errback(self, failure, request):
        if self.debug:
            print "HttpDownloadHandler: errback called!"
            print failure.getErrorMessage()
            failure.getBriefTraceback()
            failure.printTraceback()

        if failure.check(TimeoutError):
            raise defer.TimeoutError
