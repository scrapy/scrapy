from urlparse import urlparse, urlunparse

from twisted.python import failure
from twisted.web.client import HTTPClientFactory, PartialDownloadError
from twisted.web.http import HTTPClient
from twisted.internet import defer

from scrapy.http import Headers
from scrapy.utils.httpobj import urlparse_cached

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

    def handleHeader(self, key, value):
        self.headers.appendlist(key, value)

    def handleStatus(self, version, status, message):
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
        self.factory.noPage(defer.TimeoutError("Getting %s took longer than %s seconds." % (self.factory.url, self.factory.timeout)))


class ScrapyHTTPClientFactory(HTTPClientFactory):
    """Scrapy implementation of the HTTPClientFactory overwriting the
    serUrl method to make use of our Url object that cache the parse 
    result.
    """

    protocol = ScrapyHTTPPageGetter
    response_headers = None
    waiting = 1
    noisy = False

    def __init__(self, url, method='GET', body=None, headers=None, timeout=0, parsedurl=None):
        self.url = url
        self.method = method
        self.body = body or None
        if parsedurl:
            self.scheme, self.netloc, self.host, self.port, self.path = _parsed_url_args(parsedurl)
        else:
            self.scheme, self.netloc, self.host, self.port, self.path = _parse(url)

        self.timeout = timeout
        self.headers = Headers(headers or {})
        self.deferred = defer.Deferred()

        # set Host header based on url
        self.headers.setdefault('Host', self.netloc)

        # set Content-Length based len of body
        if self.body is not None:
            self.headers['Content-Length'] = len(self.body)
            # just in case a broken http/1.1 decides to keep connection alive
            self.headers.setdefault("Connection", "close")

    @classmethod
    def from_request(cls, request, timeout):
        return cls(request.url,
            method=request.method,
            body=request.body or None, # see http://dev.scrapy.org/ticket/60
            headers=Headers(request.headers or {}),
            timeout=timeout,
            parsedurl=urlparse_cached(request),
            )

    def gotHeaders(self, headers):
        self.response_headers = headers



def getPage(url, contextFactory=None, *args, **kwargs):
    """
    Download a web page as a string.

    Download a page. Return a deferred, which will callback with a
    page (as a string) or errback with a description of the error.

    See HTTPClientFactory to see what extra args can be passed.
    """
    from twisted.web.client import _makeGetterFactory
    return _makeGetterFactory(
        url,
        ScrapyHTTPClientFactory,
        contextFactory=contextFactory,
        *args, **kwargs).deferred
