import re
from time import time
from urllib.parse import urldefrag, urlparse, urlunparse

import scrapy
from twisted.internet import defer
from twisted.internet.protocol import ClientFactory
from twisted.web.http import HTTPClient

from scrapy.responsetypes import responsetypes
from scrapy.utils.httpobj import urlparse_cached


def _parsed_url_args(parsed):
    """
    Returns a tuple of (scheme, netloc, host, port, path), where everything except the port is in bytes, and port is an
    integer. Assumes that 'parsed' argument was parsed from a Request.url received via safe_url_string, and is ascii-only.
    """
    path = urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    path = scrapy.utils.python.to_bytes(path, encoding="ascii")
    host = scrapy.utils.python.to_bytes(parsed.hostname, encoding="ascii")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    scheme = scrapy.utils.python.to_bytes(parsed.scheme, encoding="ascii")
    netloc = scrapy.utils.python.to_bytes(parsed.netloc, encoding="ascii")
    return scheme, netloc, host, port, path


def parse_url(url):
    """
    Returns a tuple of (scheme, netloc, host, port, path), where everything except the port is in bytes, and port is an
    integer. Assumes that 'url' argument came from Request.url and is ascii-only.
    """
    url = url.strip()
    if not re.match(r"^\w+://", url):
        url = "//" + url
    parsed = urlparse(url)
    return _parsed_url_args(parsed)


class ScrapyHTTPPageGetter(HTTPClient):

    delimiter = b"\n"

    def connectionMade(self):
        self.headers = scrapy.http.Headers()

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
        return super().lineReceived(line.rstrip())

    def handleHeader(self, key, value):
        self.headers.appendlist(key, value)

    def handleStatus(self, version, status, message):
        self.factory.gotStatus(version, status, message)

    def handleEndHeaders(self):
        self.factory.gotHeaders(self.headers)

    def connectionLost(self, reason):
        self.factory.noPage(reason)
        super().connectionLost(reason)

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

        # Transport cleanup needed for HTTPS connections
        if self.factory.url.startswith(b"https"):
            self.transport.stopProducing()

        self.factory.noPage(
            defer.TimeoutError(
                f"Getting {self.factory.url} took longer than {self.factory.timeout} seconds."
            )
        )


class ScrapyHTTPClientFactory(ClientFactory):

    protocol = ScrapyHTTPPageGetter

    waiting = 1
    noisy = False
    followRedirect = False
    afterFoundGet = False

    def __init__(self, request, timeout=180):
        self._url = urldefrag(request.url)[0]
        # Could not 'to_bytes' the entire url, because urldefrag() requires Unicode input,
        # and converted characters would become percent-encoded. Instead, only the scheme,
        # hostname, netloc, and path were converted. The remaining bit (fragment identifier)
        # is assumed to not have any characters requiring conversion.
        parsed_url = urlparse(self._url)
        self.url = urlunparse(
            (
                scrapy.utils.python.to_bytes(parsed_url.scheme, encoding="ascii"),
                "",
                scrapy.utils.python.to_bytes(parsed_url.netloc, encoding="ascii"),
                "",
                "",
                "",
            )
        )
        self.method = scrapy.utils.python.to_bytes(request.method, encoding="ascii")
        self.body = request.body or None
        self.headers = scrapy.http.Headers(request.headers)
        self.response_headers = None
        self.timeout = request.meta.get("download_timeout", timeout)
        self.start_time = time()
        self.deferred = defer.Deferred().addCallback(self._build_response, request)

        # Fixes Twisted 11.1.0+ support as HTTPClientFactory is expected
        # to have _disconnectedDeferred. See Twisted r32329.
        # As Scrapy implements its own logic to handle redirects is not
        # needed to add the callback _waitForDisconnect.
        # Specifically this avoids the AttributeError exception when
        # clientConnectionFailed method is called.
        self._disconnectedDeferred = defer.Deferred()

        # Set Host header based on url
        self.headers.setdefault("Host", urlparse_cached(request).hostname)

        # Set Content-Length based len of body
        if self.body is not None:
            self.headers["Content-Length"] = str(len(self.body)).encode("utf-8")
            # Just in case a broken http/1.1 decides to keep connection alive
            self.headers.setdefault("Connection", "close")
        # Content-Length must be specified in POST method even with no body
        elif self.method == b"POST":
            self.headers["Content-Length"] = b"0"

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.url}>"

    def buildProtocol(self, addr):
        p = super().buildProtocol(addr)
        p.followRedirect = self.followRedirect
        p.afterFoundGet = self.afterFoundGet
        if self.timeout:
            from twisted.internet import reactor

            timeoutCall = reactor.callLater(self.timeout, p.timeout)
            self.deferred.addBoth(self._cancelTimeout, timeoutCall)
        return p

    def _cancelTimeout(self, result, timeoutCall):
        if timeoutCall.active():
            timeoutCall.cancel()
        return result

    def _set_connection_attributes(self, request):
        parsed = urlparse_cached(request)
        self.scheme, _, self.host, self.port, self.path = _parsed_url_args(parsed)
        proxy = request.meta.get("proxy")
        if proxy:
            self.scheme, _, self.host, self.port, _ = parse_url(proxy)
            self.path = self.url

    def _build_response(self, body, request):
        request.meta["download_latency"] = self.headers_time - self.start_time
        status = int(self.status)
        headers = scrapy.http.Headers(self.response_headers)
        respcls = responsetypes.from_args(headers=headers, url=self._url, body=body)
        return respcls(
            url=self._url,
            status=status,
            headers=headers,
            body=body,
            protocol=scrapy.utils.python.to_unicode(self.version),
        )

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