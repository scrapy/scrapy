from time import time
from urlparse import urlparse, urlunparse, urldefrag
from twisted.internet.ssl import ClientContextFactory

from twisted.python import failure
from twisted.web.client import PartialDownloadError, HTTPClientFactory
from twisted.web.http import HTTPClient
from twisted.internet import defer

from scrapy.http import Headers
from scrapy.utils.httpobj import urlparse_cached
from scrapy.responsetypes import responsetypes
from scrapy import log

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


class ScrapyHTTPPageGetter(HTTPClient):

    delimiter = '\n'

    def connectionMade(self):
        self.headers = Headers() # bucket for response headers

        if self.factory.use_tunnel:
            log.msg("Sending CONNECT", log.DEBUG)
            self.tunnel_started = False
            self.sendCommand("CONNECT", "%s:%s"
                % (self.factory.tunnel_to_host, self.factory.tunnel_to_port))
            self.sendHeaders(only=['Host','Proxy-Connection', 'User-Agent'])
            del self.factory.headers['Proxy-Connection']
        else:
            self.sendEverything()


    def sendCommand(self, command, path):
        if self.factory.use_tunnel and not self.tunnel_started:
            http_version = "1.1"
        else:
            http_version = "1.0"
        self.transport.write('%s %s HTTP/%s\r\n' % (command, path, http_version))


    def sendEverything(self):
        self.sendMethod()
        self.sendHeaders()
        self.sendBody()

    def sendMethod(self):
        # Method command
        self.sendCommand(self.factory.method, self.factory.path)

    def sendHeaders(self, only=None):
        # Note: it's a Headers object, not a dict
        keys = only if only is not None else self.factory.headers.keys()
        for key in keys:
            for value in self.factory.headers.getlist(key):
                self.sendHeader(key, value)
        self.endHeaders()

    def sendBody(self):
        # Body
        if self.factory.body is not None:
            self.transport.write(self.factory.body)

    def lineReceived(self, line):
        if self.factory.use_tunnel and not self.tunnel_started: log.msg("LINE: %s" % line)
        if self.factory.use_tunnel and not self.tunnel_started and not line.rstrip():
            # End of headers from the proxy in response to our CONNECT request
            # Skip the call to HTTPClient.lienReceived for now, since otherwise
            # it would switch to row mode.
            self.startTunnel()
        else:
            return HTTPClient.lineReceived(self, line.rstrip())

    def startTunnel(self):

        log.msg("starting Tunnel")

        # We'll get a new batch of headers through the tunnel. This sets us
        # up to capture them.
        self.firstLine = True
        self.tunnel_started = True

        # Switch to SSL
        ctx = ClientContextFactory()
        self.transport.startTLS(ctx, self.factory)

        # And send the normal request:
        self.sendEverything()


    def handleHeader(self, key, value):
        if self.factory.use_tunnel and not self.tunnel_started:
            pass # maybe log headers for CONNECT request?
        else:
            self.headers.appendlist(key, value)

    def handleStatus(self, version, status, message):
        if self.factory.use_tunnel and not self.tunnel_started:
            self.tunnel_status = status
        else:
            self.factory.gotStatus(version, status, message)

    def handleEndHeaders(self):
        self.factory.gotHeaders(self.headers)

    def connectionLost(self, reason):
        HTTPClient.connectionLost(self, reason)
        self.factory.noPage(reason)

    def handleResponse(self, response):
        if self.factory.method.upper() == 'HEAD':
            self.factory.page('')
        elif self.length != None and self.length != 0:
            self.factory.noPage(failure.Failure(
                PartialDownloadError(self.factory.status, None, response)))
        else:
            self.factory.page(response)
        self.transport.loseConnection()

    def timeout(self):
        self.transport.loseConnection()
        self.factory.noPage(\
                defer.TimeoutError("Getting %s took longer than %s seconds." % \
                (self.factory.url, self.factory.timeout)))


class ScrapyHTTPClientFactory(HTTPClientFactory):
    """Scrapy implementation of the HTTPClientFactory overwriting the
    serUrl method to make use of our Url object that cache the parse 
    result.
    """

    protocol = ScrapyHTTPPageGetter
    waiting = 1
    noisy = False
    followRedirect = False
    afterFoundGet = False

    def __init__(self, request, timeout=180):
        self.url = urldefrag(request.url)[0]
        self.method = request.method
        self.body = request.body or None
        self.headers = Headers(request.headers)
        self.response_headers = None
        self.timeout = request.meta.get('download_timeout') or timeout
        self.start_time = time()
        self.deferred = defer.Deferred().addCallback(self._build_response, request)

        self._set_connection_attributes(request)

        # set Host header based on url
        self.headers.setdefault('Host', self.netloc)

        # set Content-Length based len of body
        if self.body is not None:
            self.headers['Content-Length'] = len(self.body)
            # just in case a broken http/1.1 decides to keep connection alive
            self.headers.setdefault("Connection", "close")

    def _build_response(self, body, request):
        request.meta['download_latency'] = self.headers_time-self.start_time
        status = int(self.status)
        headers = Headers(self.response_headers)
        respcls = responsetypes.from_args(headers=headers, url=self.url)
        return respcls(url=self.url, status=status, headers=headers, body=body)

    def _set_connection_attributes(self, request):
        parsed = urlparse_cached(request)
        self.scheme, self.netloc, self.host, self.port, self.path = _parsed_url_args(parsed)
        self.use_tunnel = False
        proxy = request.meta.get('proxy')
        if proxy:
            old_scheme, old_host, old_port = self.scheme, self.host, self.port
            self.scheme, _, self.host, self.port, _ = _parse(proxy)
            self.path = self.url
            if old_scheme=="https":
                self.headers['Proxy-Connection'] = 'keep-alive'
                self.use_tunnel = True
                self.tunnel_to_host = old_host
                self.tunnel_to_port = old_port

    def gotHeaders(self, headers):
        self.headers_time = time()
        self.response_headers = headers
