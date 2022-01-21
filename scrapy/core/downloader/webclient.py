import re
from time import time
from urllib.parse import urlparse, urlunparse, urldefrag

from twisted.web.http import HTTPClient
from twisted.internet import defer
from twisted.internet.protocol import ClientFactory

from scrapy.http import Headers
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes, to_unicode
from scrapy.responsetypes import responsetypes


def _parsed_url_args(parsed):
    # Assume parsed is urlparse-d from Request.url,
    # which was passed via safe_url_string and is ascii-only.
    path = urlunparse(('', '', parsed.path or '/', parsed.params, parsed.query, ''))
    path = to_bytes(path, encoding="ascii")
    host = to_bytes(parsed.hostname, encoding="ascii")
    port = parsed.port
    scheme = to_bytes(parsed.scheme, encoding="ascii")
    netloc = to_bytes(parsed.netloc, encoding="ascii")
    if port is None:
        port = 443 if scheme == b'https' else 80
    return scheme, netloc, host, port, path


def _parse(url):
    """ Return tuple of (scheme, netloc, host, port, path),
    all in bytes except for port which is int.
    Assume url is from Request.url, which was passed via safe_url_string
    and is ascii-only.
    """
    url = url.strip()
    if not re.match(r'^\w+://', url):
        url = '//' + url
    parsed = urlparse(url)
    return _parsed_url_args(parsed)


class ScrapyHTTPPageGetter(HTTPClient):

    delimiter = b'\n'

    def connectionMade(self):
        self.headers = Headers()  # bucket for response headers

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
        if self.factory.method.upper() == b'HEAD':
            self.factory.page(b'')
        elif self.length is not None and self.length > 0:
            self.factory.noPage(self._connection_lost_reason)
        else:
            self.factory.page(response)
        self.transport.loseConnection()

    def timeout(self):
        self.transport.loseConnection()

        # transport cleanup needed for HTTPS connections
        if self.factory.url.startswith(b'https'):
            self.transport.stopProducing()

        self.factory.noPage(
            defer.TimeoutError(f"Getting {self.factory.url} took longer "
                               f"than {self.factory.timeout} seconds."))


# This class used to inherit from Twisted’s
# twisted.web.client.HTTPClientFactory. When that class was deprecated in
# Twisted (https://github.com/twisted/twisted/pull/643), we merged its
# non-overriden code into this class.
class ScrapyHTTPClientFactory(ClientFactory):

    protocol = ScrapyHTTPPageGetter

    waiting = 1
    noisy = False
    followRedirect = False
    afterFoundGet = False

    def _build_response(self, body, request):
        request.meta['download_latency'] = self.headers_time - self.start_time
        status = int(self.status)
        headers = Headers(self.response_headers)
        respcls = responsetypes.from_args(headers=headers, url=self._url)
        return respcls(url=self._url, status=status, headers=headers, body=body, protocol=to_unicode(self.version))

    def _set_connection_attributes(self, request):
        parsed = urlparse_cached(request)
        self.scheme, self.netloc, self.host, self.port, self.path = _parsed_url_args(parsed)
        proxy = request.meta.get('proxy')
        if proxy:
            self.scheme, _, self.host, self.port, _ = _parse(proxy)
            self.path = self.url

    def __init__(self, request, timeout=180):
        self._url = urldefrag(request.url)[0]
        # converting to bytes to comply to Twisted interface
        self.url = to_bytes(self._url, encoding='ascii')
        self.method = to_bytes(request.method, encoding='ascii')
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
        elif self.method == b'POST':
            self.headers['Content-Length'] = 0

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.url}>"

    def _cancelTimeout(self, result, timeoutCall):
        if timeoutCall.active():
            timeoutCall.cancel()
        return result

    def buildProtocol(self, addr):
        p = ClientFactory.buildProtocol(self, addr)
        p.followRedirect = self.followRedirect
        p.afterFoundGet = self.afterFoundGet
        if self.timeout:
            from twisted.internet import reactor
            timeoutCall = reactor.callLater(self.timeout, p.timeout)
            self.deferred.addBoth(self._cancelTimeout, timeoutCall)
        return p

    def gotHeaders(self, headers):
        self.headers_time = time()
        self.response_headers = headers

    def gotStatus(self, version, status, message):
        """
        Set the status of the request on us.
        @param version: The HTTP version.
        @type version: L{bytes}
        @param status: The HTTP status code, an integer represented as a
            bytestring.
        @type status: L{bytes}
        @param message: The HTTP status message.
        @type message: L{bytes}
        """
        self.version, self.status, self.message = version, status, message

    def page(self, page):
        if self.waiting:
            self.waiting = 0
            self.deferred.callback(page)

    def noPage(self, reason):
        if self.waiting:
            self.waiting = 0
            self.deferred.errback(reason)

    def clientConnectionFailed(self, _, reason):
        """
        When a connection attempt fails, the request cannot be issued.  If no
        result has yet been provided to the result Deferred, provide the
        connection failure reason as an error result.
        """
        if self.waiting:
            self.waiting = 0
            # If the connection attempt failed, there is nothing more to
            # disconnect, so just fire that Deferred now.
            self._disconnectedDeferred.callback(None)
            self.deferred.errback(reason)
