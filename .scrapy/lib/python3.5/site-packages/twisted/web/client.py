# -*- test-case-name: twisted.web.test.test_webclient,twisted.web.test.test_agent -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTTP client.
"""

from __future__ import division, absolute_import

import os
import warnings

try:
    from urlparse import urlunparse, urljoin, urldefrag
except ImportError:
    from urllib.parse import urljoin, urldefrag
    from urllib.parse import urlunparse as _urlunparse

    def urlunparse(parts):
        result = _urlunparse(tuple([p.decode("charmap") for p in parts]))
        return result.encode("charmap")

import zlib
from functools import wraps

from zope.interface import implementer

from twisted.python import log
from twisted.python.compat import _PY3, networkString
from twisted.python.compat import nativeString, intToBytes, unicode, itervalues
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.failure import Failure
from twisted.python.versions import Version

from twisted.web.iweb import IPolicyForHTTPS, IAgentEndpointFactory
from twisted.python.deprecate import getDeprecationWarningString
from twisted.web import http
from twisted.internet import defer, protocol, task, reactor
from twisted.internet.abstract import isIPv6Address
from twisted.internet.interfaces import IProtocol, IOpenSSLContextFactory
from twisted.internet.endpoints import TCP4ClientEndpoint, SSL4ClientEndpoint
from twisted.python.util import InsensitiveDict
from twisted.python.components import proxyForInterface
from twisted.web import error
from twisted.web.iweb import UNKNOWN_LENGTH, IAgent, IBodyProducer, IResponse
from twisted.web.http_headers import Headers


class PartialDownloadError(error.Error):
    """
    Page was only partially downloaded, we got disconnected in middle.

    @ivar response: All of the response body which was downloaded.
    """


class HTTPPageGetter(http.HTTPClient):
    """
    Gets a resource via HTTP, then quits.

    Typically used with L{HTTPClientFactory}.  Note that this class does not, by
    itself, do anything with the response.  If you want to download a resource
    into a file, use L{HTTPPageDownloader} instead.

    @ivar _completelyDone: A boolean indicating whether any further requests are
        necessary after this one completes in order to provide a result to
        C{self.factory.deferred}.  If it is C{False}, then a redirect is going
        to be followed.  Otherwise, this protocol's connection is the last one
        before firing the result Deferred.  This is used to make sure the result
        Deferred is only fired after the connection is cleaned up.
    """

    quietLoss = 0
    followRedirect = True
    failed = 0

    _completelyDone = True

    _specialHeaders = set((b'host', b'user-agent', b'cookie', b'content-length'))

    def connectionMade(self):
        method = getattr(self.factory, 'method', b'GET')
        self.sendCommand(method, self.factory.path)
        if self.factory.scheme == b'http' and self.factory.port != 80:
            host = self.factory.host + b':' + intToBytes(self.factory.port)
        elif self.factory.scheme == b'https' and self.factory.port != 443:
            host = self.factory.host + b':' + intToBytes(self.factory.port)
        else:
            host = self.factory.host
        self.sendHeader(b'Host', self.factory.headers.get(b"host", host))
        self.sendHeader(b'User-Agent', self.factory.agent)
        data = getattr(self.factory, 'postdata', None)
        if data is not None:
            self.sendHeader(b"Content-Length", intToBytes(len(data)))

        cookieData = []
        for (key, value) in self.factory.headers.items():
            if key.lower() not in self._specialHeaders:
                # we calculated it on our own
                self.sendHeader(key, value)
            if key.lower() == b'cookie':
                cookieData.append(value)
        for cookie, cookval in self.factory.cookies.items():
            cookieData.append(cookie + b'=' + cookval)
        if cookieData:
            self.sendHeader(b'Cookie', b'; '.join(cookieData))
        self.endHeaders()
        self.headers = {}

        if data is not None:
            self.transport.write(data)

    def handleHeader(self, key, value):
        """
        Called every time a header is received. Stores the header information
        as key-value pairs in the C{headers} attribute.

        @type key: C{str}
        @param key: An HTTP header field name.

        @type value: C{str}
        @param value: An HTTP header field value.
        """
        key = key.lower()
        l = self.headers.setdefault(key, [])
        l.append(value)

    def handleStatus(self, version, status, message):
        """
        Handle the HTTP status line.

        @param version: The HTTP version.
        @type version: L{bytes}
        @param status: The HTTP status code, an integer represented as a
            bytestring.
        @type status: L{bytes}
        @param message: The HTTP status message.
        @type message: L{bytes}
        """
        self.version, self.status, self.message = version, status, message
        self.factory.gotStatus(version, status, message)

    def handleEndHeaders(self):
        self.factory.gotHeaders(self.headers)
        m = getattr(self, 'handleStatus_' + nativeString(self.status),
                    self.handleStatusDefault)
        m()

    def handleStatus_200(self):
        pass

    handleStatus_201 = lambda self: self.handleStatus_200()
    handleStatus_202 = lambda self: self.handleStatus_200()

    def handleStatusDefault(self):
        self.failed = 1

    def handleStatus_301(self):
        l = self.headers.get(b'location')
        if not l:
            self.handleStatusDefault()
            return
        url = l[0]
        if self.followRedirect:
            self.factory._redirectCount += 1
            if self.factory._redirectCount >= self.factory.redirectLimit:
                err = error.InfiniteRedirection(
                    self.status,
                    b'Infinite redirection detected',
                    location=url)
                self.factory.noPage(Failure(err))
                self.quietLoss = True
                self.transport.loseConnection()
                return

            self._completelyDone = False
            self.factory.setURL(url)

            if self.factory.scheme == b'https':
                from twisted.internet import ssl
                contextFactory = ssl.ClientContextFactory()
                reactor.connectSSL(nativeString(self.factory.host),
                                   self.factory.port,
                                   self.factory, contextFactory)
            else:
                reactor.connectTCP(nativeString(self.factory.host),
                                   self.factory.port,
                                   self.factory)
        else:
            self.handleStatusDefault()
            self.factory.noPage(
                Failure(
                    error.PageRedirect(
                        self.status, self.message, location = url)))
        self.quietLoss = True
        self.transport.loseConnection()

    def handleStatus_302(self):
        if self.afterFoundGet:
            self.handleStatus_303()
        else:
            self.handleStatus_301()


    def handleStatus_303(self):
        self.factory.method = b'GET'
        self.handleStatus_301()


    def connectionLost(self, reason):
        """
        When the connection used to issue the HTTP request is closed, notify the
        factory if we have not already, so it can produce a result.
        """
        if not self.quietLoss:
            http.HTTPClient.connectionLost(self, reason)
            self.factory.noPage(reason)
        if self._completelyDone:
            # Only if we think we're completely done do we tell the factory that
            # we're "disconnected".  This way when we're following redirects,
            # only the last protocol used will fire the _disconnectedDeferred.
            self.factory._disconnectedDeferred.callback(None)


    def handleResponse(self, response):
        if self.quietLoss:
            return
        if self.failed:
            self.factory.noPage(
                Failure(
                    error.Error(
                        self.status, self.message, response)))
        if self.factory.method == b'HEAD':
            # Callback with empty string, since there is never a response
            # body for HEAD requests.
            self.factory.page(b'')
        elif self.length != None and self.length != 0:
            self.factory.noPage(Failure(
                PartialDownloadError(self.status, self.message, response)))
        else:
            self.factory.page(response)
        # server might be stupid and not close connection. admittedly
        # the fact we do only one request per connection is also
        # stupid...
        self.transport.loseConnection()

    def timeout(self):
        self.quietLoss = True
        self.transport.abortConnection()
        self.factory.noPage(defer.TimeoutError("Getting %s took longer than %s seconds." % (self.factory.url, self.factory.timeout)))


class HTTPPageDownloader(HTTPPageGetter):

    transmittingPage = 0

    def handleStatus_200(self, partialContent=0):
        HTTPPageGetter.handleStatus_200(self)
        self.transmittingPage = 1
        self.factory.pageStart(partialContent)

    def handleStatus_206(self):
        self.handleStatus_200(partialContent=1)

    def handleResponsePart(self, data):
        if self.transmittingPage:
            self.factory.pagePart(data)

    def handleResponseEnd(self):
        if self.length:
            self.transmittingPage = 0
            self.factory.noPage(
                Failure(
                    PartialDownloadError(self.status)))
        if self.transmittingPage:
            self.factory.pageEnd()
            self.transmittingPage = 0
        if self.failed:
            self.factory.noPage(
                Failure(
                    error.Error(
                        self.status, self.message, None)))
            self.transport.loseConnection()


class HTTPClientFactory(protocol.ClientFactory):
    """Download a given URL.

    @type deferred: Deferred
    @ivar deferred: A Deferred that will fire when the content has
          been retrieved. Once this is fired, the ivars `status', `version',
          and `message' will be set.

    @type status: bytes
    @ivar status: The status of the response.

    @type version: bytes
    @ivar version: The version of the response.

    @type message: bytes
    @ivar message: The text message returned with the status.

    @type response_headers: dict
    @ivar response_headers: The headers that were specified in the
          response from the server.

    @type method: bytes
    @ivar method: The HTTP method to use in the request.  This should be one of
        OPTIONS, GET, HEAD, POST, PUT, DELETE, TRACE, or CONNECT (case
        matters).  Other values may be specified if the server being contacted
        supports them.

    @type redirectLimit: int
    @ivar redirectLimit: The maximum number of HTTP redirects that can occur
          before it is assumed that the redirection is endless.

    @type afterFoundGet: C{bool}
    @ivar afterFoundGet: Deviate from the HTTP 1.1 RFC by handling redirects
        the same way as most web browsers; if the request method is POST and a
        302 status is encountered, the redirect is followed with a GET method

    @type _redirectCount: int
    @ivar _redirectCount: The current number of HTTP redirects encountered.

    @ivar _disconnectedDeferred: A L{Deferred} which only fires after the last
        connection associated with the request (redirects may cause multiple
        connections to be required) has closed.  The result Deferred will only
        fire after this Deferred, so that callers can be assured that there are
        no more event sources in the reactor once they get the result.
    """

    protocol = HTTPPageGetter

    url = None
    scheme = None
    host = b''
    port = None
    path = None

    def __init__(self, url, method=b'GET', postdata=None, headers=None,
                 agent=b"Twisted PageGetter", timeout=0, cookies=None,
                 followRedirect=True, redirectLimit=20,
                 afterFoundGet=False):
        self.followRedirect = followRedirect
        self.redirectLimit = redirectLimit
        self._redirectCount = 0
        self.timeout = timeout
        self.agent = agent
        self.afterFoundGet = afterFoundGet
        if cookies is None:
            cookies = {}
        self.cookies = cookies
        if headers is not None:
            self.headers = InsensitiveDict(headers)
        else:
            self.headers = InsensitiveDict()
        if postdata is not None:
            self.headers.setdefault(b'Content-Length',
                                    intToBytes(len(postdata)))
            # just in case a broken http/1.1 decides to keep connection alive
            self.headers.setdefault(b"connection", b"close")
        self.postdata = postdata
        self.method = method

        self.setURL(url)

        self.waiting = 1
        self._disconnectedDeferred = defer.Deferred()
        self.deferred = defer.Deferred()
        # Make sure the first callback on the result Deferred pauses the
        # callback chain until the request connection is closed.
        self.deferred.addBoth(self._waitForDisconnect)
        self.response_headers = None


    def _waitForDisconnect(self, passthrough):
        """
        Chain onto the _disconnectedDeferred, preserving C{passthrough}, so that
        the result is only available after the associated connection has been
        closed.
        """
        self._disconnectedDeferred.addCallback(lambda ignored: passthrough)
        return self._disconnectedDeferred


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.url)

    def setURL(self, url):
        self.url = url
        uri = URI.fromBytes(url)
        if uri.scheme and uri.host:
            self.scheme = uri.scheme
            self.host = uri.host
            self.port = uri.port
        self.path = uri.originForm

    def buildProtocol(self, addr):
        p = protocol.ClientFactory.buildProtocol(self, addr)
        p.followRedirect = self.followRedirect
        p.afterFoundGet = self.afterFoundGet
        if self.timeout:
            timeoutCall = reactor.callLater(self.timeout, p.timeout)
            self.deferred.addBoth(self._cancelTimeout, timeoutCall)
        return p

    def _cancelTimeout(self, result, timeoutCall):
        if timeoutCall.active():
            timeoutCall.cancel()
        return result

    def gotHeaders(self, headers):
        self.response_headers = headers
        if b'set-cookie' in headers:
            for cookie in headers[b'set-cookie']:
                cookparts = cookie.split(b';')
                cook = cookparts[0]
                cook.lstrip()
                k, v = cook.split(b'=', 1)
                self.cookies[k.lstrip()] = v.lstrip()

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



class HTTPDownloader(HTTPClientFactory):
    """
    Download to a file.
    """
    protocol = HTTPPageDownloader
    value = None

    def __init__(self, url, fileOrName,
                 method=b'GET', postdata=None, headers=None,
                 agent=b"Twisted client", supportPartial=False,
                 timeout=0, cookies=None, followRedirect=True,
                 redirectLimit=20, afterFoundGet=False):
        self.requestedPartial = 0
        if isinstance(fileOrName, (str, unicode)):
            self.fileName = fileOrName
            self.file = None
            if supportPartial and os.path.exists(self.fileName):
                fileLength = os.path.getsize(self.fileName)
                if fileLength:
                    self.requestedPartial = fileLength
                    if headers == None:
                        headers = {}
                    headers[b"range"] = b"bytes=" + intToBytes(fileLength) + b"-"
        else:
            self.file = fileOrName
        HTTPClientFactory.__init__(
            self, url, method=method, postdata=postdata, headers=headers,
            agent=agent, timeout=timeout, cookies=cookies,
            followRedirect=followRedirect, redirectLimit=redirectLimit,
            afterFoundGet=afterFoundGet)


    def gotHeaders(self, headers):
        HTTPClientFactory.gotHeaders(self, headers)
        if self.requestedPartial:
            contentRange = headers.get(b"content-range", None)
            if not contentRange:
                # server doesn't support partial requests, oh well
                self.requestedPartial = 0
                return
            start, end, realLength = http.parseContentRange(contentRange[0])
            if start != self.requestedPartial:
                # server is acting weirdly
                self.requestedPartial = 0


    def openFile(self, partialContent):
        if partialContent:
            file = open(self.fileName, 'rb+')
            file.seek(0, 2)
        else:
            file = open(self.fileName, 'wb')
        return file

    def pageStart(self, partialContent):
        """Called on page download start.

        @param partialContent: tells us if the download is partial download we requested.
        """
        if partialContent and not self.requestedPartial:
            raise ValueError("we shouldn't get partial content response if we didn't want it!")
        if self.waiting:
            try:
                if not self.file:
                    self.file = self.openFile(partialContent)
            except IOError:
                #raise
                self.deferred.errback(Failure())

    def pagePart(self, data):
        if not self.file:
            return
        try:
            self.file.write(data)
        except IOError:
            #raise
            self.file = None
            self.deferred.errback(Failure())


    def noPage(self, reason):
        """
        Close the storage file and errback the waiting L{Deferred} with the
        given reason.
        """
        if self.waiting:
            self.waiting = 0
            if self.file:
                try:
                    self.file.close()
                except:
                    log.err(None, "Error closing HTTPDownloader file")
            self.deferred.errback(reason)


    def pageEnd(self):
        self.waiting = 0
        if not self.file:
            return
        try:
            self.file.close()
        except IOError:
            self.deferred.errback(Failure())
            return
        self.deferred.callback(self.value)



class URI(object):
    """
    A URI object.

    @see: U{https://tools.ietf.org/html/draft-ietf-httpbis-p1-messaging-21}
    """
    def __init__(self, scheme, netloc, host, port, path, params, query,
                 fragment):
        """
        @type scheme: L{bytes}
        @param scheme: URI scheme specifier.

        @type netloc: L{bytes}
        @param netloc: Network location component.

        @type host: L{bytes}
        @param host: Host name. For IPv6 address literals the brackets are
            stripped.

        @type port: L{int}
        @param port: Port number.

        @type path: L{bytes}
        @param path: Hierarchical path.

        @type params: L{bytes}
        @param params: Parameters for last path segment.

        @type query: L{bytes}
        @param query: Query string.

        @type fragment: L{bytes}
        @param fragment: Fragment identifier.
        """
        self.scheme = scheme
        self.netloc = netloc
        self.host = host.strip(b'[]')
        self.port = port
        self.path = path
        self.params = params
        self.query = query
        self.fragment = fragment


    @classmethod
    def fromBytes(cls, uri, defaultPort=None):
        """
        Parse the given URI into a L{URI}.

        @type uri: C{bytes}
        @param uri: URI to parse.

        @type defaultPort: C{int} or L{None}
        @param defaultPort: An alternate value to use as the port if the URI
            does not include one.

        @rtype: L{URI}
        @return: Parsed URI instance.
        """
        uri = uri.strip()
        scheme, netloc, path, params, query, fragment = http.urlparse(uri)

        if defaultPort is None:
            if scheme == b'https':
                defaultPort = 443
            else:
                defaultPort = 80

        if b':' in netloc:
            host, port = netloc.rsplit(b':', 1)
            try:
                port = int(port)
            except ValueError:
                host, port = netloc, defaultPort
        else:
            host, port = netloc, defaultPort
        return cls(scheme, netloc, host, port, path, params, query, fragment)


    def toBytes(self):
        """
        Assemble the individual parts of the I{URI} into a fully formed I{URI}.

        @rtype: C{bytes}
        @return: A fully formed I{URI}.
        """
        return urlunparse(
            (self.scheme, self.netloc, self.path, self.params, self.query,
             self.fragment))


    @property
    def originForm(self):
        """
        The absolute I{URI} path including I{URI} parameters, query string and
        fragment identifier.

        @see: U{https://tools.ietf.org/html/draft-ietf-httpbis-p1-messaging-21#section-5.3}

        @return: The absolute path in original form.
        @rtype: L{bytes}
        """
        # The HTTP bis draft says the origin form should not include the
        # fragment.
        path = urlunparse(
            (b'', b'', self.path, self.params, self.query, b''))
        if path == b'':
            path = b'/'
        return path



def _urljoin(base, url):
    """
    Construct a full ("absolute") URL by combining a "base URL" with another
    URL. Informally, this uses components of the base URL, in particular the
    addressing scheme, the network location and (part of) the path, to provide
    missing components in the relative URL.

    Additionally, the fragment identifier is preserved according to the HTTP
    1.1 bis draft.

    @type base: C{bytes}
    @param base: Base URL.

    @type url: C{bytes}
    @param url: URL to combine with C{base}.

    @return: An absolute URL resulting from the combination of C{base} and
        C{url}.

    @see: L{urlparse.urljoin}

    @see: U{https://tools.ietf.org/html/draft-ietf-httpbis-p2-semantics-22#section-7.1.2}
    """
    base, baseFrag = urldefrag(base)
    url, urlFrag = urldefrag(urljoin(base, url))
    return urljoin(url, b'#' + (urlFrag or baseFrag))



def _makeGetterFactory(url, factoryFactory, contextFactory=None,
                       *args, **kwargs):
    """
    Create and connect an HTTP page getting factory.

    Any additional positional or keyword arguments are used when calling
    C{factoryFactory}.

    @param factoryFactory: Factory factory that is called with C{url}, C{args}
        and C{kwargs} to produce the getter

    @param contextFactory: Context factory to use when creating a secure
        connection, defaulting to L{None}

    @return: The factory created by C{factoryFactory}
    """
    uri = URI.fromBytes(url)
    factory = factoryFactory(url, *args, **kwargs)
    if uri.scheme == b'https':
        from twisted.internet import ssl
        if contextFactory is None:
            contextFactory = ssl.ClientContextFactory()
        reactor.connectSSL(
            nativeString(uri.host), uri.port, factory, contextFactory)
    else:
        reactor.connectTCP(nativeString(uri.host), uri.port, factory)
    return factory


def getPage(url, contextFactory=None, *args, **kwargs):
    """
    Download a web page as a string.

    Download a page. Return a deferred, which will callback with a
    page (as a string) or errback with a description of the error.

    See L{HTTPClientFactory} to see what extra arguments can be passed.
    """
    return _makeGetterFactory(
        url,
        HTTPClientFactory,
        contextFactory=contextFactory,
        *args, **kwargs).deferred


def downloadPage(url, file, contextFactory=None, *args, **kwargs):
    """
    Download a web page to a file.

    @param file: path to file on filesystem, or file-like object.

    See HTTPDownloader to see what extra args can be passed.
    """
    factoryFactory = lambda url, *a, **kw: HTTPDownloader(url, file, *a, **kw)
    return _makeGetterFactory(
        url,
        factoryFactory,
        contextFactory=contextFactory,
        *args, **kwargs).deferred


# The code which follows is based on the new HTTP client implementation.  It
# should be significantly better than anything above, though it is not yet
# feature equivalent.

from twisted.web.error import SchemeNotSupported
from twisted.web._newclient import Request, Response, HTTP11ClientProtocol
from twisted.web._newclient import ResponseDone, ResponseFailed
from twisted.web._newclient import RequestNotSent, RequestTransmissionFailed
from twisted.web._newclient import (
    ResponseNeverReceived, PotentialDataLoss, _WrapperException)



try:
    from OpenSSL import SSL
except ImportError:
    SSL = None
else:
    from twisted.internet.ssl import (CertificateOptions,
                                      platformTrust,
                                      optionsForClientTLS)


def _requireSSL(decoratee):
    """
    The decorated method requires pyOpenSSL to be present, or it raises
    L{NotImplementedError}.

    @param decoratee: A function which requires pyOpenSSL.
    @type decoratee: L{callable}

    @return: A function which raises L{NotImplementedError} if pyOpenSSL is not
        installed; otherwise, if it is installed, simply return C{decoratee}.
    @rtype: L{callable}
    """
    if SSL is None:
        @wraps(decoratee)
        def raiseNotImplemented(*a, **kw):
            """
            pyOpenSSL is not available.

            @param a: The positional arguments for C{decoratee}.

            @param kw: The keyword arguments for C{decoratee}.

            @raise NotImplementedError: Always.
            """
            raise NotImplementedError("SSL support unavailable")
        return raiseNotImplemented
    return decoratee



class WebClientContextFactory(object):
    """
    This class is deprecated.  Please simply use L{Agent} as-is, or if you want
    to customize something, use L{BrowserLikePolicyForHTTPS}.

    A L{WebClientContextFactory} is an HTTPS policy which totally ignores the
    hostname and port.  It performs basic certificate verification, however the
    lack of validation of service identity (e.g.  hostname validation) means it
    is still vulnerable to man-in-the-middle attacks.  Don't use it any more.
    """

    def _getCertificateOptions(self, hostname, port):
        """
        Return a L{CertificateOptions}.

        @param hostname: ignored

        @param port: ignored

        @return: A new CertificateOptions instance.
        @rtype: L{CertificateOptions}
        """
        return CertificateOptions(
            method=SSL.SSLv23_METHOD,
            trustRoot=platformTrust()
        )


    @_requireSSL
    def getContext(self, hostname, port):
        """
        Return an L{OpenSSL.SSL.Context}.

        @param hostname: ignored
        @param port: ignored

        @return: A new SSL context.
        @rtype: L{OpenSSL.SSL.Context}
        """
        return self._getCertificateOptions(hostname, port).getContext()



@implementer(IPolicyForHTTPS)
class BrowserLikePolicyForHTTPS(object):
    """
    SSL connection creator for web clients.
    """
    def __init__(self, trustRoot=None):
        self._trustRoot = trustRoot


    @_requireSSL
    def creatorForNetloc(self, hostname, port):
        """
        Create a L{client connection creator
        <twisted.internet.interfaces.IOpenSSLClientConnectionCreator>} for a
        given network location.

        @param tls: The TLS protocol to create a connection for.
        @type tls: L{twisted.protocols.tls.TLSMemoryBIOProtocol}

        @param hostname: The hostname part of the URI.
        @type hostname: L{bytes}

        @param port: The port part of the URI.
        @type port: L{int}

        @return: a connection creator with appropriate verification
            restrictions set
        @rtype: L{client connection creator
            <twisted.internet.interfaces.IOpenSSLClientConnectionCreator>}
        """
        return optionsForClientTLS(hostname.decode("ascii"),
                                   trustRoot=self._trustRoot)



deprecatedModuleAttribute(Version("Twisted", 14, 0, 0),
                          getDeprecationWarningString(
                              WebClientContextFactory,
                              Version("Twisted", 14, 0, 0),
                              replacement=BrowserLikePolicyForHTTPS)
                          .split("; ")[1],
                          WebClientContextFactory.__module__,
                          WebClientContextFactory.__name__)



@implementer(IOpenSSLContextFactory)
class _ContextFactoryWithContext(object):
    """
    A L{_ContextFactoryWithContext} is like a
    L{twisted.internet.ssl.ContextFactory} with a pre-created context.

    @ivar _context: A Context.
    @type _context: L{OpenSSL.SSL.Context}
    """

    def __init__(self, context):
        """
        Initialize a L{_ContextFactoryWithContext} with a context.

        @param context: An SSL context.
        @type context: L{OpenSSL.SSL.Context}
        """
        self._context = context


    def getContext(self):
        """
        Return the context created by
        L{_DeprecatedToCurrentPolicyForHTTPS._webContextFactory}.

        @return: A context.
        @rtype context: L{OpenSSL.SSL.Context}
        """
        return self._context



@implementer(IPolicyForHTTPS)
class _DeprecatedToCurrentPolicyForHTTPS(object):
    """
    Adapt a web context factory to a normal context factory.

    @ivar _webContextFactory: An object providing a getContext method with
        C{hostname} and C{port} arguments.
    @type _webContextFactory: L{WebClientContextFactory} (or object with a
        similar C{getContext} method).
    """
    def __init__(self, webContextFactory):
        """
        Wrap a web context factory in an L{IPolicyForHTTPS}.

        @param webContextFactory: An object providing a getContext method with
            C{hostname} and C{port} arguments.
        @type webContextFactory: L{WebClientContextFactory} (or object with a
            similar C{getContext} method).
        """
        self._webContextFactory = webContextFactory


    def creatorForNetloc(self, hostname, port):
        """
        Called the wrapped web context factory's C{getContext} method with a
        hostname and port number and return the resulting context object.

        @param hostname: The hostname part of the URI.
        @type hostname: L{bytes}

        @param port: The port part of the URI.
        @type port: L{int}

        @return: A context factory.
        @rtype: L{IOpenSSLContextFactory}
        """
        context = self._webContextFactory.getContext(hostname, port)
        return _ContextFactoryWithContext(context)



@implementer(IBodyProducer)
class FileBodyProducer(object):
    """
    L{FileBodyProducer} produces bytes from an input file object incrementally
    and writes them to a consumer.

    Since file-like objects cannot be read from in an event-driven manner,
    L{FileBodyProducer} uses a L{Cooperator} instance to schedule reads from
    the file.  This process is also paused and resumed based on notifications
    from the L{IConsumer} provider being written to.

    The file is closed after it has been read, or if the producer is stopped
    early.

    @ivar _inputFile: Any file-like object, bytes read from which will be
        written to a consumer.

    @ivar _cooperate: A method like L{Cooperator.cooperate} which is used to
        schedule all reads.

    @ivar _readSize: The number of bytes to read from C{_inputFile} at a time.
    """

    def __init__(self, inputFile, cooperator=task, readSize=2 ** 16):
        self._inputFile = inputFile
        self._cooperate = cooperator.cooperate
        self._readSize = readSize
        self.length = self._determineLength(inputFile)


    def _determineLength(self, fObj):
        """
        Determine how many bytes can be read out of C{fObj} (assuming it is not
        modified from this point on).  If the determination cannot be made,
        return C{UNKNOWN_LENGTH}.
        """
        try:
            seek = fObj.seek
            tell = fObj.tell
        except AttributeError:
            return UNKNOWN_LENGTH
        originalPosition = tell()
        seek(0, os.SEEK_END)
        end = tell()
        seek(originalPosition, os.SEEK_SET)
        return end - originalPosition


    def stopProducing(self):
        """
        Permanently stop writing bytes from the file to the consumer by
        stopping the underlying L{CooperativeTask}.
        """
        self._inputFile.close()
        self._task.stop()


    def startProducing(self, consumer):
        """
        Start a cooperative task which will read bytes from the input file and
        write them to C{consumer}.  Return a L{Deferred} which fires after all
        bytes have been written.

        @param consumer: Any L{IConsumer} provider
        """
        self._task = self._cooperate(self._writeloop(consumer))
        d = self._task.whenDone()
        def maybeStopped(reason):
            # IBodyProducer.startProducing's Deferred isn't support to fire if
            # stopProducing is called.
            reason.trap(task.TaskStopped)
            return defer.Deferred()
        d.addCallbacks(lambda ignored: None, maybeStopped)
        return d


    def _writeloop(self, consumer):
        """
        Return an iterator which reads one chunk of bytes from the input file
        and writes them to the consumer for each time it is iterated.
        """
        while True:
            bytes = self._inputFile.read(self._readSize)
            if not bytes:
                self._inputFile.close()
                break
            consumer.write(bytes)
            yield None


    def pauseProducing(self):
        """
        Temporarily suspend copying bytes from the input file to the consumer
        by pausing the L{CooperativeTask} which drives that activity.
        """
        self._task.pause()


    def resumeProducing(self):
        """
        Undo the effects of a previous C{pauseProducing} and resume copying
        bytes to the consumer by resuming the L{CooperativeTask} which drives
        the write activity.
        """
        self._task.resume()



class _HTTP11ClientFactory(protocol.Factory):
    """
    A factory for L{HTTP11ClientProtocol}, used by L{HTTPConnectionPool}.

    @ivar _quiescentCallback: The quiescent callback to be passed to protocol
        instances, used to return them to the connection pool.

    @since: 11.1
    """
    def __init__(self, quiescentCallback):
        self._quiescentCallback = quiescentCallback


    def buildProtocol(self, addr):
        return HTTP11ClientProtocol(self._quiescentCallback)



class _RetryingHTTP11ClientProtocol(object):
    """
    A wrapper for L{HTTP11ClientProtocol} that automatically retries requests.

    @ivar _clientProtocol: The underlying L{HTTP11ClientProtocol}.

    @ivar _newConnection: A callable that creates a new connection for a
        retry.
    """

    def __init__(self, clientProtocol, newConnection):
        self._clientProtocol = clientProtocol
        self._newConnection = newConnection


    def _shouldRetry(self, method, exception, bodyProducer):
        """
        Indicate whether request should be retried.

        Only returns C{True} if method is idempotent, no response was
        received, the reason for the failed request was not due to
        user-requested cancellation, and no body was sent. The latter
        requirement may be relaxed in the future, and PUT added to approved
        method list.

        @param method: The method of the request.
        @type method: L{bytes}
        """
        if method not in (b"GET", b"HEAD", b"OPTIONS", b"DELETE", b"TRACE"):
            return False
        if not isinstance(exception, (RequestNotSent,
                                      RequestTransmissionFailed,
                                      ResponseNeverReceived)):
            return False
        if isinstance(exception, _WrapperException):
            for aFailure in exception.reasons:
                if aFailure.check(defer.CancelledError):
                    return False
        if bodyProducer is not None:
            return False
        return True


    def request(self, request):
        """
        Do a request, and retry once (with a new connection) if it fails in
        a retryable manner.

        @param request: A L{Request} instance that will be requested using the
            wrapped protocol.
        """
        d = self._clientProtocol.request(request)

        def failed(reason):
            if self._shouldRetry(request.method, reason.value,
                                 request.bodyProducer):
                return self._newConnection().addCallback(
                    lambda connection: connection.request(request))
            else:
                return reason
        d.addErrback(failed)
        return d



class HTTPConnectionPool(object):
    """
    A pool of persistent HTTP connections.

    Features:
     - Cached connections will eventually time out.
     - Limits on maximum number of persistent connections.

    Connections are stored using keys, which should be chosen such that any
    connections stored under a given key can be used interchangeably.

    Failed requests done using previously cached connections will be retried
    once if they use an idempotent method (e.g. GET), in case the HTTP server
    timed them out.

    @ivar persistent: Boolean indicating whether connections should be
        persistent. Connections are persistent by default.

    @ivar maxPersistentPerHost: The maximum number of cached persistent
        connections for a C{host:port} destination.
    @type maxPersistentPerHost: C{int}

    @ivar cachedConnectionTimeout: Number of seconds a cached persistent
        connection will stay open before disconnecting.

    @ivar retryAutomatically: C{boolean} indicating whether idempotent
        requests should be retried once if no response was received.

    @ivar _factory: The factory used to connect to the proxy.

    @ivar _connections: Map (scheme, host, port) to lists of
        L{HTTP11ClientProtocol} instances.

    @ivar _timeouts: Map L{HTTP11ClientProtocol} instances to a
        C{IDelayedCall} instance of their timeout.

    @since: 12.1
    """

    _factory = _HTTP11ClientFactory
    maxPersistentPerHost = 2
    cachedConnectionTimeout = 240
    retryAutomatically = True

    def __init__(self, reactor, persistent=True):
        self._reactor = reactor
        self.persistent = persistent
        self._connections = {}
        self._timeouts = {}


    def getConnection(self, key, endpoint):
        """
        Supply a connection, newly created or retrieved from the pool, to be
        used for one HTTP request.

        The connection will remain out of the pool (not available to be
        returned from future calls to this method) until one HTTP request has
        been completed over it.

        Afterwards, if the connection is still open, it will automatically be
        added to the pool.

        @param key: A unique key identifying connections that can be used
            interchangeably.

        @param endpoint: An endpoint that can be used to open a new connection
            if no cached connection is available.

        @return: A C{Deferred} that will fire with a L{HTTP11ClientProtocol}
           (or a wrapper) that can be used to send a single HTTP request.
        """
        # Try to get cached version:
        connections = self._connections.get(key)
        while connections:
            connection = connections.pop(0)
            # Cancel timeout:
            self._timeouts[connection].cancel()
            del self._timeouts[connection]
            if connection.state == "QUIESCENT":
                if self.retryAutomatically:
                    newConnection = lambda: self._newConnection(key, endpoint)
                    connection = _RetryingHTTP11ClientProtocol(
                        connection, newConnection)
                return defer.succeed(connection)

        return self._newConnection(key, endpoint)


    def _newConnection(self, key, endpoint):
        """
        Create a new connection.

        This implements the new connection code path for L{getConnection}.
        """
        def quiescentCallback(protocol):
            self._putConnection(key, protocol)
        factory = self._factory(quiescentCallback)
        return endpoint.connect(factory)


    def _removeConnection(self, key, connection):
        """
        Remove a connection from the cache and disconnect it.
        """
        connection.transport.loseConnection()
        self._connections[key].remove(connection)
        del self._timeouts[connection]


    def _putConnection(self, key, connection):
        """
        Return a persistent connection to the pool. This will be called by
        L{HTTP11ClientProtocol} when the connection becomes quiescent.
        """
        if connection.state != "QUIESCENT":
            # Log with traceback for debugging purposes:
            try:
                raise RuntimeError(
                    "BUG: Non-quiescent protocol added to connection pool.")
            except:
                log.err()
            return
        connections = self._connections.setdefault(key, [])
        if len(connections) == self.maxPersistentPerHost:
            dropped = connections.pop(0)
            dropped.transport.loseConnection()
            self._timeouts[dropped].cancel()
            del self._timeouts[dropped]
        connections.append(connection)
        cid = self._reactor.callLater(self.cachedConnectionTimeout,
                                      self._removeConnection,
                                      key, connection)
        self._timeouts[connection] = cid


    def closeCachedConnections(self):
        """
        Close all persistent connections and remove them from the pool.

        @return: L{defer.Deferred} that fires when all connections have been
            closed.
        """
        results = []
        for protocols in itervalues(self._connections):
            for p in protocols:
                results.append(p.abort())
        self._connections = {}
        for dc in itervalues(self._timeouts):
            dc.cancel()
        self._timeouts = {}
        return defer.gatherResults(results).addCallback(lambda ign: None)



class _AgentBase(object):
    """
    Base class offering common facilities for L{Agent}-type classes.

    @ivar _reactor: The C{IReactorTime} implementation which will be used by
        the pool, and perhaps by subclasses as well.

    @ivar _pool: The L{HTTPConnectionPool} used to manage HTTP connections.
    """

    def __init__(self, reactor, pool):
        if pool is None:
            pool = HTTPConnectionPool(reactor, False)
        self._reactor = reactor
        self._pool = pool


    def _computeHostValue(self, scheme, host, port):
        """
        Compute the string to use for the value of the I{Host} header, based on
        the given scheme, host name, and port number.
        """
        if (isIPv6Address(nativeString(host))):
            host = b'[' + host + b']'
        if (scheme, port) in ((b'http', 80), (b'https', 443)):
            return host
        return host + b":" + intToBytes(port)


    def _requestWithEndpoint(self, key, endpoint, method, parsedURI,
                             headers, bodyProducer, requestPath):
        """
        Issue a new request, given the endpoint and the path sent as part of
        the request.
        """
        # Create minimal headers, if necessary:
        if headers is None:
            headers = Headers()
        if not headers.hasHeader(b'host'):
            headers = headers.copy()
            headers.addRawHeader(
                b'host', self._computeHostValue(parsedURI.scheme,
                                                parsedURI.host,
                                                parsedURI.port))

        d = self._pool.getConnection(key, endpoint)
        def cbConnected(proto):
            return proto.request(
                Request._construct(method, requestPath, headers, bodyProducer,
                                   persistent=self._pool.persistent,
                                   parsedURI=parsedURI))
        d.addCallback(cbConnected)
        return d



@implementer(IAgentEndpointFactory)
class _StandardEndpointFactory(object):
    """
    Standard HTTP endpoint destinations - TCP for HTTP, TCP+TLS for HTTPS.

    @ivar _policyForHTTPS: A web context factory which will be used to create
        SSL context objects for any SSL connections the agent needs to make.

    @ivar _connectTimeout: If not L{None}, the timeout passed to
        L{TCP4ClientEndpoint} or C{SSL4ClientEndpoint} for specifying the
        connection timeout.

    @ivar _bindAddress: If not L{None}, the address passed to
        L{TCP4ClientEndpoint} or C{SSL4ClientEndpoint} for specifying the local
        address to bind to.
    """
    def __init__(self, reactor, contextFactory, connectTimeout, bindAddress):
        """
        @param reactor: A provider of
            L{twisted.internet.interfaces.IReactorTCP} and
            L{twisted.internet.interfaces.IReactorSSL} for this L{Agent} to
            place outgoing connections.
        @type reactor: L{twisted.internet.interfaces.IReactorTCP} and
            L{twisted.internet.interfaces.IReactorSSL}

        @param contextFactory: A factory for TLS contexts, to control the
            verification parameters of OpenSSL.
        @type contextFactory: L{IPolicyForHTTPS}.

        @param connectTimeout: The amount of time that this L{Agent} will wait
            for the peer to accept a connection.
        @type connectTimeout: L{float} or L{None}

        @param bindAddress: The local address for client sockets to bind to.
        @type bindAddress: L{bytes} or L{None}
        """
        self._reactor = reactor
        self._policyForHTTPS = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress


    def endpointForURI(self, uri):
        """
        Connect directly over TCP for C{b'http'} scheme, and TLS for C{b'https'}.

        @param uri: L{URI} to connect to.

        @return: Endpoint to connect to.
        @rtype: L{TCP4ClientEndpoint} or L{SSL4ClientEndpoint}
        """
        kwargs = {}
        if self._connectTimeout is not None:
            kwargs['timeout'] = self._connectTimeout
        kwargs['bindAddress'] = self._bindAddress

        try:
            host = nativeString(uri.host)
        except UnicodeDecodeError:
            raise ValueError(("The host of the provided URI ({uri.host!r}) "
                              "contains non-ASCII octets, it should be ASCII "
                              "decodable.").format(uri=uri))

        if uri.scheme == b'http':
            return TCP4ClientEndpoint(self._reactor, host, uri.port, **kwargs)
        elif uri.scheme == b'https':
            tlsPolicy = self._policyForHTTPS.creatorForNetloc(uri.host,
                                                              uri.port)
            return SSL4ClientEndpoint(self._reactor, host, uri.port, tlsPolicy,
                                      **kwargs)
        else:
            raise SchemeNotSupported("Unsupported scheme: %r" % (uri.scheme,))



@implementer(IAgent)
class Agent(_AgentBase):
    """
    L{Agent} is a very basic HTTP client.  It supports I{HTTP} and I{HTTPS}
    scheme URIs.

    @ivar _pool: An L{HTTPConnectionPool} instance.

    @ivar _endpointFactory: The L{IAgentEndpointFactory} which will
        be used to create endpoints for outgoing connections.

    @since: 9.0
    """

    def __init__(self, reactor,
                 contextFactory=BrowserLikePolicyForHTTPS(),
                 connectTimeout=None, bindAddress=None,
                 pool=None):
        """
        Create an L{Agent}.

        @param reactor: A provider of
            L{twisted.internet.interfaces.IReactorTCP} and
            L{twisted.internet.interfaces.IReactorSSL} for this L{Agent} to
            place outgoing connections.
        @type reactor: L{twisted.internet.interfaces.IReactorTCP} and
            L{twisted.internet.interfaces.IReactorSSL}

        @param contextFactory: A factory for TLS contexts, to control the
            verification parameters of OpenSSL.  The default is to use a
            L{BrowserLikePolicyForHTTPS}, so unless you have special
            requirements you can leave this as-is.
        @type contextFactory: L{IPolicyForHTTPS}.

        @param connectTimeout: The amount of time that this L{Agent} will wait
            for the peer to accept a connection.
        @type connectTimeout: L{float}

        @param bindAddress: The local address for client sockets to bind to.
        @type bindAddress: L{bytes}

        @param pool: An L{HTTPConnectionPool} instance, or L{None}, in which
            case a non-persistent L{HTTPConnectionPool} instance will be
            created.
        @type pool: L{HTTPConnectionPool}
        """
        if not IPolicyForHTTPS.providedBy(contextFactory):
            warnings.warn(
                repr(contextFactory) +
                " was passed as the HTTPS policy for an Agent, but it does "
                "not provide IPolicyForHTTPS.  Since Twisted 14.0, you must "
                "pass a provider of IPolicyForHTTPS.",
                stacklevel=2, category=DeprecationWarning
            )
            contextFactory = _DeprecatedToCurrentPolicyForHTTPS(contextFactory)
        endpointFactory = _StandardEndpointFactory(
            reactor, contextFactory, connectTimeout, bindAddress)
        self._init(reactor, endpointFactory, pool)


    @classmethod
    def usingEndpointFactory(cls, reactor, endpointFactory, pool=None):
        """
        Create a new L{Agent} that will use the endpoint factory to figure
        out how to connect to the server.

        @param reactor: A provider of
            L{twisted.internet.interfaces.IReactorTime}.

        @param endpointFactory: Used to construct endpoints which the
            HTTP client will connect with.
        @type endpointFactory: an L{IAgentEndpointFactory} provider.

        @param pool: An L{HTTPConnectionPool} instance, or L{None}, in which
            case a non-persistent L{HTTPConnectionPool} instance will be
            created.
        @type pool: L{HTTPConnectionPool}

        @return: A new L{Agent}.
        """
        agent = cls.__new__(cls)
        agent._init(reactor, endpointFactory, pool)
        return agent


    def _init(self, reactor, endpointFactory, pool):
        """
        Initialize a new L{Agent}.

        @param reactor: A provider of relevant reactor interfaces, at a minimum
            L{twisted.internet.interfaces.IReactorTime}.

        @param endpointFactory: Used to construct endpoints which the
            HTTP client will connect with.
        @type endpointFactory: an L{IAgentEndpointFactory} provider.

        @param pool: An L{HTTPConnectionPool} instance, or L{None}, in which
            case a non-persistent L{HTTPConnectionPool} instance will be
            created.
        @type pool: L{HTTPConnectionPool}

        @return: A new L{Agent}.
        """
        _AgentBase.__init__(self, reactor, pool)
        self._endpointFactory = endpointFactory


    def _getEndpoint(self, uri):
        """
        Get an endpoint for the given URI, using C{self._endpointFactory}.

        @param uri: The URI of the request.
        @type uri: L{URI}

        @return: An endpoint which can be used to connect to given address.
        """
        return self._endpointFactory.endpointForURI(uri)


    def request(self, method, uri, headers=None, bodyProducer=None):
        """
        Issue a request to the server indicated by the given C{uri}.

        An existing connection from the connection pool may be used or a new
        one may be created.

        I{HTTP} and I{HTTPS} schemes are supported in C{uri}.

        @see: L{twisted.web.iweb.IAgent.request}
        """
        parsedURI = URI.fromBytes(uri)
        try:
            endpoint = self._getEndpoint(parsedURI)
        except SchemeNotSupported:
            return defer.fail(Failure())
        key = (parsedURI.scheme, parsedURI.host, parsedURI.port)
        return self._requestWithEndpoint(key, endpoint, method, parsedURI,
                                         headers, bodyProducer,
                                         parsedURI.originForm)



@implementer(IAgent)
class ProxyAgent(_AgentBase):
    """
    An HTTP agent able to cross HTTP proxies.

    @ivar _proxyEndpoint: The endpoint used to connect to the proxy.

    @since: 11.1
    """

    def __init__(self, endpoint, reactor=None, pool=None):
        if reactor is None:
            from twisted.internet import reactor
        _AgentBase.__init__(self, reactor, pool)
        self._proxyEndpoint = endpoint


    def request(self, method, uri, headers=None, bodyProducer=None):
        """
        Issue a new request via the configured proxy.
        """
        # Cache *all* connections under the same key, since we are only
        # connecting to a single destination, the proxy:
        key = ("http-proxy", self._proxyEndpoint)

        # To support proxying HTTPS via CONNECT, we will use key
        # ("http-proxy-CONNECT", scheme, host, port), and an endpoint that
        # wraps _proxyEndpoint with an additional callback to do the CONNECT.
        return self._requestWithEndpoint(key, self._proxyEndpoint, method,
                                         URI.fromBytes(uri), headers,
                                         bodyProducer, uri)



class _FakeUrllib2Request(object):
    """
    A fake C{urllib2.Request} object for C{cookielib} to work with.

    @see: U{http://docs.python.org/library/urllib2.html#request-objects}

    @type uri: native L{str}
    @ivar uri: Request URI.

    @type headers: L{twisted.web.http_headers.Headers}
    @ivar headers: Request headers.

    @type type: native L{str}
    @ivar type: The scheme of the URI.

    @type host: native L{str}
    @ivar host: The host[:port] of the URI.

    @since: 11.1
    """
    def __init__(self, uri):
        """
        Create a fake Urllib2 request.

        @param uri: Request URI.
        @type uri: L{bytes}
        """
        self.uri = nativeString(uri)
        self.headers = Headers()

        _uri = URI.fromBytes(uri)
        self.type = nativeString(_uri.scheme)
        self.host = nativeString(_uri.host)

        if (_uri.scheme, _uri.port) not in ((b'http', 80), (b'https', 443)):
            # If it's not a schema on the regular port, add the port.
            self.host += ":" + str(_uri.port)

        if _PY3:
            self.origin_req_host = nativeString(_uri.host)
            self.unverifiable = lambda _: False


    def has_header(self, header):
        return self.headers.hasHeader(networkString(header))


    def add_unredirected_header(self, name, value):
        self.headers.addRawHeader(networkString(name), networkString(value))


    def get_full_url(self):
        return self.uri


    def get_header(self, name, default=None):
        headers = self.headers.getRawHeaders(networkString(name), default)
        if headers is not None:
            headers = [nativeString(x) for x in headers]
            return headers[0]
        return None


    def get_host(self):
        return self.host


    def get_type(self):
        return self.type


    def is_unverifiable(self):
        # In theory this shouldn't be hardcoded.
        return False



class _FakeUrllib2Response(object):
    """
    A fake C{urllib2.Response} object for C{cookielib} to work with.

    @type response: C{twisted.web.iweb.IResponse}
    @ivar response: Underlying Twisted Web response.

    @since: 11.1
    """
    def __init__(self, response):
        self.response = response


    def info(self):
        class _Meta(object):
            def getheaders(zelf, name):
                # PY2
                headers = self.response.headers.getRawHeaders(name, [])
                return headers
            def get_all(zelf, name, default):
                # PY3
                headers = self.response.headers.getRawHeaders(
                    networkString(name), default)
                h = [nativeString(x) for x in headers]
                return h
        return _Meta()



@implementer(IAgent)
class CookieAgent(object):
    """
    L{CookieAgent} extends the basic L{Agent} to add RFC-compliant
    handling of HTTP cookies.  Cookies are written to and extracted
    from a C{cookielib.CookieJar} instance.

    The same cookie jar instance will be used for any requests through this
    agent, mutating it whenever a I{Set-Cookie} header appears in a response.

    @type _agent: L{twisted.web.client.Agent}
    @ivar _agent: Underlying Twisted Web agent to issue requests through.

    @type cookieJar: C{cookielib.CookieJar}
    @ivar cookieJar: Initialized cookie jar to read cookies from and store
        cookies to.

    @since: 11.1
    """
    def __init__(self, agent, cookieJar):
        self._agent = agent
        self.cookieJar = cookieJar


    def request(self, method, uri, headers=None, bodyProducer=None):
        """
        Issue a new request to the wrapped L{Agent}.

        Send a I{Cookie} header if a cookie for C{uri} is stored in
        L{CookieAgent.cookieJar}. Cookies are automatically extracted and
        stored from requests.

        If a C{'cookie'} header appears in C{headers} it will override the
        automatic cookie header obtained from the cookie jar.

        @see: L{Agent.request}
        """
        if headers is None:
            headers = Headers()
        lastRequest = _FakeUrllib2Request(uri)
        # Setting a cookie header explicitly will disable automatic request
        # cookies.
        if not headers.hasHeader(b'cookie'):
            self.cookieJar.add_cookie_header(lastRequest)
            cookieHeader = lastRequest.get_header('Cookie', None)
            if cookieHeader is not None:
                headers = headers.copy()
                headers.addRawHeader(b'cookie', networkString(cookieHeader))

        d = self._agent.request(method, uri, headers, bodyProducer)
        d.addCallback(self._extractCookies, lastRequest)
        return d


    def _extractCookies(self, response, request):
        """
        Extract response cookies and store them in the cookie jar.

        @type response: L{twisted.web.iweb.IResponse}
        @param response: Twisted Web response.

        @param request: A urllib2 compatible request object.
        """
        resp = _FakeUrllib2Response(response)
        self.cookieJar.extract_cookies(resp, request)
        return response



class GzipDecoder(proxyForInterface(IResponse)):
    """
    A wrapper for a L{Response} instance which handles gzip'ed body.

    @ivar original: The original L{Response} object.

    @since: 11.1
    """

    def __init__(self, response):
        self.original = response
        self.length = UNKNOWN_LENGTH


    def deliverBody(self, protocol):
        """
        Override C{deliverBody} to wrap the given C{protocol} with
        L{_GzipProtocol}.
        """
        self.original.deliverBody(_GzipProtocol(protocol, self.original))



class _GzipProtocol(proxyForInterface(IProtocol)):
    """
    A L{Protocol} implementation which wraps another one, transparently
    decompressing received data.

    @ivar _zlibDecompress: A zlib decompress object used to decompress the data
        stream.

    @ivar _response: A reference to the original response, in case of errors.

    @since: 11.1
    """

    def __init__(self, protocol, response):
        self.original = protocol
        self._response = response
        self._zlibDecompress = zlib.decompressobj(16 + zlib.MAX_WBITS)


    def dataReceived(self, data):
        """
        Decompress C{data} with the zlib decompressor, forwarding the raw data
        to the original protocol.
        """
        try:
            rawData = self._zlibDecompress.decompress(data)
        except zlib.error:
            raise ResponseFailed([Failure()], self._response)
        if rawData:
            self.original.dataReceived(rawData)


    def connectionLost(self, reason):
        """
        Forward the connection lost event, flushing remaining data from the
        decompressor if any.
        """
        try:
            rawData = self._zlibDecompress.flush()
        except zlib.error:
            raise ResponseFailed([reason, Failure()], self._response)
        if rawData:
            self.original.dataReceived(rawData)
        self.original.connectionLost(reason)



@implementer(IAgent)
class ContentDecoderAgent(object):
    """
    An L{Agent} wrapper to handle encoded content.

    It takes care of declaring the support for content in the
    I{Accept-Encoding} header, and automatically decompresses the received data
    if it's effectively using compression.

    @param decoders: A list or tuple of (name, decoder) objects. The name
        declares which decoding the decoder supports, and the decoder must
        return a response object when called/instantiated. For example,
        C{(('gzip', GzipDecoder))}. The order determines how the decoders are
        going to be advertized to the server.

    @since: 11.1
    """

    def __init__(self, agent, decoders):
        self._agent = agent
        self._decoders = dict(decoders)
        self._supported = b','.join([decoder[0] for decoder in decoders])


    def request(self, method, uri, headers=None, bodyProducer=None):
        """
        Send a client request which declares supporting compressed content.

        @see: L{Agent.request}.
        """
        if headers is None:
            headers = Headers()
        else:
            headers = headers.copy()
        headers.addRawHeader(b'accept-encoding', self._supported)
        deferred = self._agent.request(method, uri, headers, bodyProducer)
        return deferred.addCallback(self._handleResponse)


    def _handleResponse(self, response):
        """
        Check if the response is encoded, and wrap it to handle decompression.
        """
        contentEncodingHeaders = response.headers.getRawHeaders(
            b'content-encoding', [])
        contentEncodingHeaders = b','.join(contentEncodingHeaders).split(b',')
        while contentEncodingHeaders:
            name = contentEncodingHeaders.pop().strip()
            decoder = self._decoders.get(name)
            if decoder is not None:
                response = decoder(response)
            else:
                # Add it back
                contentEncodingHeaders.append(name)
                break
        if contentEncodingHeaders:
            response.headers.setRawHeaders(
                b'content-encoding', [b','.join(contentEncodingHeaders)])
        else:
            response.headers.removeHeader(b'content-encoding')
        return response



@implementer(IAgent)
class RedirectAgent(object):
    """
    An L{Agent} wrapper which handles HTTP redirects.

    The implementation is rather strict: 301 and 302 behaves like 307, not
    redirecting automatically on methods different from I{GET} and I{HEAD}.

    See L{BrowserLikeRedirectAgent} for a redirecting Agent that behaves more
    like a web browser.

    @param redirectLimit: The maximum number of times the agent is allowed to
        follow redirects before failing with a L{error.InfiniteRedirection}.

    @cvar _redirectResponses: A L{list} of HTTP status codes to be redirected
        for I{GET} and I{HEAD} methods.

    @cvar _seeOtherResponses: A L{list} of HTTP status codes to be redirected
        for any method and the method altered to I{GET}.

    @since: 11.1
    """

    _redirectResponses = [http.MOVED_PERMANENTLY, http.FOUND,
                          http.TEMPORARY_REDIRECT]
    _seeOtherResponses = [http.SEE_OTHER]


    def __init__(self, agent, redirectLimit=20):
        self._agent = agent
        self._redirectLimit = redirectLimit


    def request(self, method, uri, headers=None, bodyProducer=None):
        """
        Send a client request following HTTP redirects.

        @see: L{Agent.request}.
        """
        deferred = self._agent.request(method, uri, headers, bodyProducer)
        return deferred.addCallback(
            self._handleResponse, method, uri, headers, 0)


    def _resolveLocation(self, requestURI, location):
        """
        Resolve the redirect location against the request I{URI}.

        @type requestURI: C{bytes}
        @param requestURI: The request I{URI}.

        @type location: C{bytes}
        @param location: The redirect location.

        @rtype: C{bytes}
        @return: Final resolved I{URI}.
        """
        return _urljoin(requestURI, location)


    def _handleRedirect(self, response, method, uri, headers, redirectCount):
        """
        Handle a redirect response, checking the number of redirects already
        followed, and extracting the location header fields.
        """
        if redirectCount >= self._redirectLimit:
            err = error.InfiniteRedirection(
                response.code,
                b'Infinite redirection detected',
                location=uri)
            raise ResponseFailed([Failure(err)], response)
        locationHeaders = response.headers.getRawHeaders(b'location', [])
        if not locationHeaders:
            err = error.RedirectWithNoLocation(
                response.code, b'No location header field', uri)
            raise ResponseFailed([Failure(err)], response)
        location = self._resolveLocation(uri, locationHeaders[0])
        deferred = self._agent.request(method, location, headers)
        def _chainResponse(newResponse):
            newResponse.setPreviousResponse(response)
            return newResponse
        deferred.addCallback(_chainResponse)
        return deferred.addCallback(
            self._handleResponse, method, uri, headers, redirectCount + 1)


    def _handleResponse(self, response, method, uri, headers, redirectCount):
        """
        Handle the response, making another request if it indicates a redirect.
        """
        if response.code in self._redirectResponses:
            if method not in (b'GET', b'HEAD'):
                err = error.PageRedirect(response.code, location=uri)
                raise ResponseFailed([Failure(err)], response)
            return self._handleRedirect(response, method, uri, headers,
                                        redirectCount)
        elif response.code in self._seeOtherResponses:
            return self._handleRedirect(response, b'GET', uri, headers,
                                        redirectCount)
        return response



class BrowserLikeRedirectAgent(RedirectAgent):
    """
    An L{Agent} wrapper which handles HTTP redirects in the same fashion as web
    browsers.

    Unlike L{RedirectAgent}, the implementation is more relaxed: 301 and 302
    behave like 303, redirecting automatically on any method and altering the
    redirect request to a I{GET}.

    @see: L{RedirectAgent}

    @since: 13.1
    """
    _redirectResponses = [http.TEMPORARY_REDIRECT]
    _seeOtherResponses = [http.MOVED_PERMANENTLY, http.FOUND, http.SEE_OTHER]



class _ReadBodyProtocol(protocol.Protocol):
    """
    Protocol that collects data sent to it.

    This is a helper for L{IResponse.deliverBody}, which collects the body and
    fires a deferred with it.

    @ivar deferred: See L{__init__}.
    @ivar status: See L{__init__}.
    @ivar message: See L{__init__}.

    @ivar dataBuffer: list of byte-strings received
    @type dataBuffer: L{list} of L{bytes}
    """

    def __init__(self, status, message, deferred):
        """
        @param status: Status of L{IResponse}
        @ivar status: L{int}

        @param message: Message of L{IResponse}
        @type message: L{bytes}

        @param deferred: deferred to fire when response is complete
        @type deferred: L{Deferred} firing with L{bytes}
        """
        self.deferred = deferred
        self.status = status
        self.message = message
        self.dataBuffer = []


    def dataReceived(self, data):
        """
        Accumulate some more bytes from the response.
        """
        self.dataBuffer.append(data)


    def connectionLost(self, reason):
        """
        Deliver the accumulated response bytes to the waiting L{Deferred}, if
        the response body has been completely received without error.
        """
        if reason.check(ResponseDone):
            self.deferred.callback(b''.join(self.dataBuffer))
        elif reason.check(PotentialDataLoss):
            self.deferred.errback(
                PartialDownloadError(self.status, self.message,
                                     b''.join(self.dataBuffer)))
        else:
            self.deferred.errback(reason)



def readBody(response):
    """
    Get the body of an L{IResponse} and return it as a byte string.

    This is a helper function for clients that don't want to incrementally
    receive the body of an HTTP response.

    @param response: The HTTP response for which the body will be read.
    @type response: L{IResponse} provider

    @return: A L{Deferred} which will fire with the body of the response.
        Cancelling it will close the connection to the server immediately.
    """
    def cancel(deferred):
        """
        Cancel a L{readBody} call, close the connection to the HTTP server
        immediately, if it is still open.

        @param deferred: The cancelled L{defer.Deferred}.
        """
        abort = getAbort()
        if abort is not None:
            abort()

    d = defer.Deferred(cancel)
    protocol = _ReadBodyProtocol(response.code, response.phrase, d)
    def getAbort():
        return getattr(protocol.transport, 'abortConnection', None)

    response.deliverBody(protocol)

    if protocol.transport is not None and getAbort() is None:
        warnings.warn(
            'Using readBody with a transport that does not have an '
            'abortConnection method',
            category=DeprecationWarning,
            stacklevel=2)

    return d



__all__ = [
    'PartialDownloadError', 'HTTPPageGetter', 'HTTPPageDownloader',
    'HTTPClientFactory', 'HTTPDownloader', 'getPage', 'downloadPage',
    'ResponseDone', 'Response', 'ResponseFailed', 'Agent', 'CookieAgent',
    'ProxyAgent', 'ContentDecoderAgent', 'GzipDecoder', 'RedirectAgent',
    'HTTPConnectionPool', 'readBody', 'BrowserLikeRedirectAgent', 'URI']
