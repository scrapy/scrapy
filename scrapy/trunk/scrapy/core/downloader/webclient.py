from urlparse import urlunparse

from twisted.web.client import HTTPClientFactory, HTTPPageGetter
from twisted.web import http
from twisted.python import failure
from twisted.web import error
from twisted.internet import defer

from scrapy.http import Url, Headers
from scrapy.utils.misc import arg_to_iter

def _parse(url, defaultPort=None):
    url = url.strip()
    try:
        parsed = url.parsedurl
    except AttributeError:
        parsed = Url(url).parsedurl

    scheme = parsed[0]
    path = urlunparse(('','')+parsed[2:])
    if defaultPort is None:
        if scheme == 'https':
            defaultPort = 443
        else:
            defaultPort = 80
    host, port = parsed[1], defaultPort
    if ':' in host:
        host, port = host.split(':')
        port = int(port)
    if path == "":
        path = "/"
    return scheme, host, port, path


class ScrapyHTTPPageGetter(HTTPPageGetter):
    quietLoss = 0
    failed = 0

    _specialHeaders = set(('host', 'user-agent', 'content-length'))

    def connectionMade(self):
        headers = self.factory.headers
        method = getattr(self.factory, 'method', 'GET')

        self.sendCommand(method, self.factory.path)
        self.sendHeader('Host', headers.get("host", self.factory.host))
        self.sendHeader('User-Agent', headers.get('User-Agent', self.factory.agent))

        data = getattr(self.factory, 'postdata', None)
        if data is not None:
            self.sendHeader("Content-Length", str(len(data)))

        for key, value in self.factory.headers.items():
            if key.lower() not in self._specialHeaders:
                self.sendHeader(key, value)

        self.endHeaders()
        self.headers = Headers()

        if data is not None:
            self.transport.write(data)

    def sendHeader(self, name, value):
        for v in arg_to_iter(value):
            self.transport.write('%s: %s\r\n' % (name, v))

    def handleHeader(self, key, value):
        self.headers.appendlist(key, value)

    def handleStatus(self, version, status, message):
        self.version, self.status, self.message = version, status, message
        self.factory.gotStatus(version, status, message)

    def handleEndHeaders(self):
        self.factory.gotHeaders(self.headers)
        m = getattr(self, 'handleStatus_'+self.status, self.handleStatusDefault)
        m()

    def handleStatus_200(self):
        pass

    handleStatus_201 = lambda self: self.handleStatus_200()
    handleStatus_202 = lambda self: self.handleStatus_200()

    def handleStatusDefault(self):
        self.failed = 1

    def connectionLost(self, reason):
        if not self.quietLoss:
            http.HTTPClient.connectionLost(self, reason)
            self.factory.noPage(reason)

    def handleResponse(self, response):
        if self.quietLoss:
            return

        if self.failed:
            self.factory.noPage(failure.Failure(error.Error(self.status, self.message, response)))

        if self.factory.method.upper() == 'HEAD':
            # Callback with empty string, since there is never a response
            # body for HEAD requests.
            self.factory.page('')
        elif self.length != None and self.length != 0:
            self.factory.noPage(failure.Failure(
                PartialDownloadError(self.status, self.message, response)))
        else:
            self.factory.page(response)

        # server might be stupid and not close connection. admittedly
        # the fact we do only one request per connection is also
        # stupid...
        self.transport.loseConnection()

    def timeout(self):
        self.quietLoss = True
        self.transport.loseConnection()
        self.factory.noPage(defer.TimeoutError("Getting %s took longer than %s seconds." % (self.factory.url, self.factory.timeout)))



class ScrapyHTTPClientFactory(HTTPClientFactory):
    """Scrapy implementation of the HTTPClientFactory overwriting the
    serUrl method to make use of our Url object that cache the parse 
    result. Also we override gotHeaders that dies when parsing malformed 
    cookies.
    """

    protocol = ScrapyHTTPPageGetter

    def setURL(self, url):
        self.url = url
        scheme, host, port, path = _parse(url)
        if scheme and host:
            self.scheme = scheme
            self.host = host
            self.port = port
        self.path = path

    def gotHeaders(self, headers):
        """
        HTTPClientFactory.gotHeaders dies when parsing malformed cookies,
        and the crawler is getting malformed cookies from this site.

        Cookies format: 
            http://www.ietf.org/rfc/rfc2109.txt
        
        I have choosen not to filter based on this, so we don't filter invalid
        values that could be managed correctly by twisted.
        """
        self.response_headers = headers

