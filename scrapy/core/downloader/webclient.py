from time import time
from six.moves.urllib.parse import urlparse, urlunparse, urldefrag

from twisted.web.client import HTTPClientFactory
from twisted.web.http import HTTPClient
from twisted.internet import defer

from scrapy.http import Headers
from scrapy.utils.httpobj import urlparse_cached
from scrapy.responsetypes import responsetypes


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

        # Method command
        self.sendCommand(self.factory.method, self.factory.path)
        # Headers
        for key, values in self.factory.headers.items():
            for value in values:
                self.sendHeader(key, value)
        self.endHeaders()
        # Body
        if self.factory.body is not None:
            self.transport.write(self.factory.body)

    def lineReceived(self, line):
        return HTTPClient.lineReceived(self, line.rstrip())

    def handleHeader(self, key, value):
        self.headers.appendlist(key, value)

    def handleStatus(self, version, status, message):
        self.factory.gotStatus(version, status, message)

    def handleEndHeaders(self):
        self.factory.gotHeaders(self.headers)

    def connectionLost(self, reason):
        self._connection_lost_reason = reason
        HTTPClient.connectionLost(self, reason)
        self.factory.noPage(reason)

    def handleResponse(self, response):
        if self.factory.method.upper() == 'HEAD':
            self.factory.page('')
        elif self.length is not None and self.length > 0:
            self.factory.noPage(self._connection_lost_reason)
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

        # Fixes Twisted 11.1.0+ support as HTTPClientFactory is expected
        # to have _disconnectedDeferred. See Twisted r32329.
        # As Scrapy implements it's own logic to handle redirects is not
        # needed to add the callback _waitForDisconnect.
        # Specifically this avoids the AttributeError exception when
        # clientConnectionFailed method is called.
        self._disconnectedDeferred = defer.Deferred()

        self._set_connection_attributes(request)

        # set Host header based on url
        self.headers.setdefault('Host', self.netloc)

        # set Content-Length based len of body
        if self.body is not None:
            self.headers['Content-Length'] = len(self.body)
            # just in case a broken http/1.1 decides to keep connection alive
            self.headers.setdefault("Connection", "close")
        # Content-Length must be specified in POST method even with no body
        elif self.method == 'POST':
            self.headers['Content-Length'] = 0

    def _build_response(self, body, request):
        request.meta['download_latency'] = self.headers_time-self.start_time
        status = int(self.status)
        headers = Headers(self.response_headers)
        respcls = responsetypes.from_args(headers=headers, url=self.url)
        return respcls(url=self.url, status=status, headers=headers, body=body)

    def _set_connection_attributes(self, request):
        parsed = urlparse_cached(request)
        self.scheme, self.netloc, self.host, self.port, self.path = _parsed_url_args(parsed)
        proxy = request.meta.get('proxy')
        if proxy:
            self.scheme, _, self.host, self.port, _ = _parse(proxy)
            self.path = self.url

    def gotHeaders(self, headers):
        self.headers_time = time()
        self.response_headers = headers

