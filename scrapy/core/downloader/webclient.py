from time import time
from six.moves.urllib.parse import urlparse, urlunparse, urldefrag

from twisted.web.client import HTTPClientFactory
from twisted.web.http import HTTPClient
from twisted.internet import defer

from scrapy.http import Headers
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes
from scrapy.responsetypes import responsetypes

from scrapy import log


def _parsed_url_args(parsed):
    # Assume parsed is urlparse-d from Request.url,
    # which was passed via safe_url_string and is ascii-only.
    b = lambda s: to_bytes(s, encoding='ascii')
    path = urlunparse(('', '', parsed.path or '/', parsed.params, parsed.query, ''))
    path = b(path)
    host = b(parsed.hostname)
    port = parsed.port
    scheme = b(parsed.scheme)
    netloc = b(parsed.netloc)
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
    parsed = urlparse(url)
    return _parsed_url_args(parsed)


class ScrapyHTTPPageGetter(HTTPClient):

    delimiter = b'\n'

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

    def _build_response(self, body, request):
        request.meta['download_latency'] = self.headers_time-self.start_time
        status = int(self.status)
        headers = Headers(self.response_headers)
        respcls = responsetypes.from_args(headers=headers, url=self._url)
        return respcls(url=self._url, status=status, headers=headers, body=body)

    def _set_connection_attributes(self, request):
        parsed = urlparse_cached(request)
        self.scheme, self.netloc, self.host, self.port, self.path = _parsed_url_args(parsed)
        self.use_tunnel = False
        proxy = request.meta.get('proxy')
        if proxy:
            old_scheme, old_host, old_port = self.scheme, self.host, self.port
            self.scheme, _, self.host, self.port, _ = _parse(proxy)
            if old_scheme=="https" and 'ssl' in optional_features:
                 self.headers['Proxy-Connection'] = 'keep-alive'
                 self.use_tunnel = True
                 self.tunnel_to_host = old_host
                 self.tunnel_to_port = old_port
            if not self.use_tunnel: self.path = self.url

    def gotHeaders(self, headers):
        self.headers_time = time()
        self.response_headers = headers

