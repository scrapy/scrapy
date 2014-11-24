# -*- test-case-name: twisted.web.test.test_webclient,twisted.web.test.test_agent -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTTP client.
"""

from __future__ import division, absolute_import

import os

try:
    from urlparse import urlunparse
    from urllib import splithost, splittype
except ImportError:
    from urllib.parse import splithost, splittype
    from urllib.parse import urlunparse as _urlunparse

    def urlunparse(parts):
        result = _urlunparse(tuple([p.decode("charmap") for p in parts]))
        return result.encode("charmap")
import zlib

from zope.interface import implementer

from twisted.python import log
from twisted.python.failure import Failure
from twisted.web import http
from twisted.internet import defer, protocol, task, reactor
from twisted.internet.interfaces import IProtocol
from twisted.python import failure
from twisted.python.components import proxyForInterface
from twisted.web import error
from twisted.web.http_headers import Headers

from .endpoints import TCP4ClientEndpoint, SSL4ClientEndpoint
from .iweb import IResponse, UNKNOWN_LENGTH, IBodyProducer


class PartialDownloadError(error.Error):
    """
    Page was only partially downloaded, we got disconnected in middle.

    @ivar response: All of the response body which was downloaded.
    """


class _URL(tuple):
    """
    A parsed URL.

    At some point this should be replaced with a better URL implementation.
    """
    def __new__(self, scheme, host, port, path):
        return tuple.__new__(_URL, (scheme, host, port, path))


    def __init__(self, scheme, host, port, path):
        self.scheme = scheme
        self.host = host
        self.port = port
        self.path = path


def _parse(url, defaultPort=None):
    """
    Split the given URL into the scheme, host, port, and path.

    @type url: C{bytes}
    @param url: An URL to parse.

    @type defaultPort: C{int} or C{None}
    @param defaultPort: An alternate value to use as the port if the URL does
    not include one.

    @return: A four-tuple of the scheme, host, port, and path of the URL.  All
    of these are C{bytes} instances except for port, which is an C{int}.
    """
    url = url.strip()
    parsed = http.urlparse(url)
    scheme = parsed[0]
    path = urlunparse((b'', b'') + parsed[2:])

    if defaultPort is None:
        if scheme == b'https':
            defaultPort = 443
        else:
            defaultPort = 80

    host, port = parsed[1], defaultPort
    if b':' in host:
        host, port = host.split(b':')
        try:
            port = int(port)
        except ValueError:
            port = defaultPort

    if path == b'':
        path = b'/'

    return _URL(scheme, host, port, path)


def _makeGetterFactory(url, factoryFactory, contextFactory=None,
                       *args, **kwargs):
    """
    Create and connect an HTTP page getting factory.

    Any additional positional or keyword arguments are used when calling
    C{factoryFactory}.

    @param factoryFactory: Factory factory that is called with C{url}, C{args}
        and C{kwargs} to produce the getter

    @param contextFactory: Context factory to use when creating a secure
        connection, defaulting to C{None}

    @return: The factory created by C{factoryFactory}
    """
    scheme, host, port, path = _parse(url)
    factory = factoryFactory(url, *args, **kwargs)
    if scheme == b'https':
        from twisted.internet import ssl
        if contextFactory is None:
            contextFactory = ssl.ClientContextFactory()
        reactor.connectSSL(host, port, factory, contextFactory)
    else:
        reactor.connectTCP(host, port, factory)
    return factory


# The code which follows is based on the new HTTP client implementation.  It
# should be significantly better than anything above, though it is not yet
# feature equivalent.

from twisted.web.error import SchemeNotSupported
from ._newclient import Request, Response, HTTP11ClientProtocol
from ._newclient import ResponseDone, ResponseFailed
from ._newclient import RequestNotSent, RequestTransmissionFailed
from ._newclient import (
    ResponseNeverReceived, PotentialDataLoss, _WrapperException)

try:
    from twisted.internet.ssl import ClientContextFactory
except ImportError:
    class WebClientContextFactory(object):
        """
        A web context factory which doesn't work because the necessary SSL
        support is missing.
        """
        def getContext(self, hostname, port):
            raise NotImplementedError("SSL support unavailable")
else:
    class WebClientContextFactory(ClientContextFactory):
        """
        A web context factory which ignores the hostname and port and does no
        certificate verification.
        """
        def getContext(self, hostname, port):
            return ClientContextFactory.getContext(self)



class _WebToNormalContextFactory(object):
    """
    Adapt a web context factory to a normal context factory.

    @ivar _webContext: A web context factory which accepts a hostname and port
        number to its C{getContext} method.

    @ivar _hostname: The hostname which will be passed to
        C{_webContext.getContext}.

    @ivar _port: The port number which will be passed to
        C{_webContext.getContext}.
    """
    def __init__(self, webContext, hostname, port):
        self._webContext = webContext
        self._hostname = hostname
        self._port = port


    def getContext(self):
        """
        Called the wrapped web context factory's C{getContext} method with a
        hostname and port number and return the resulting context object.
        """
        return self._webContext.getContext(self._hostname, self._port)



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

    # Python 2.4 doesn't have these symbolic constants
    _SEEK_SET = getattr(os, 'SEEK_SET', 0)
    _SEEK_END = getattr(os, 'SEEK_END', 2)

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
        seek(0, self._SEEK_END)
        end = tell()
        seek(originalPosition, self._SEEK_SET)
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
        """
        if method not in ("GET", "HEAD", "OPTIONS", "DELETE", "TRACE"):
            return False
        if not isinstance(exception, (RequestNotSent, RequestTransmissionFailed,
                                      ResponseNeverReceived)):
            return False
        if isinstance(exception, _WrapperException):
            for failure in exception.reasons:
                if failure.check(defer.CancelledError):
                    return False
        if bodyProducer is not None:
            return False
        return True


    def request(self, request):
        """
        Do a request, and retry once (with a new connection) it it fails in
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
        for protocols in self._connections.itervalues():
            for p in protocols:
                results.append(p.abort())
        self._connections = {}
        for dc in self._timeouts.values():
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
        if (scheme, port) in (('http', 80), ('https', 443)):
            return host
        return '%s:%d' % (host, port)


    def _requestWithEndpoint(self, key, endpoint, method, parsedURI,
                             headers, bodyProducer, requestPath):
        """
        Issue a new request, given the endpoint and the path sent as part of
        the request.
        """
        # Create minimal headers, if necessary:
        if headers is None:
            headers = Headers()
        if not headers.hasHeader('host'):
            #headers = headers.copy()  # not supported in twisted <= 11.1, and it doesn't affects us
            headers.addRawHeader(
                'host', self._computeHostValue(parsedURI.scheme, parsedURI.host,
                                               parsedURI.port))

        d = self._pool.getConnection(key, endpoint)
        def cbConnected(proto):
            return proto.request(
                Request(method, requestPath, headers, bodyProducer,
                        persistent=self._pool.persistent))
        d.addCallback(cbConnected)
        return d



class Agent(_AgentBase):
    """
    L{Agent} is a very basic HTTP client.  It supports I{HTTP} and I{HTTPS}
    scheme URIs (but performs no certificate checking by default).

    @param pool: A L{HTTPConnectionPool} instance, or C{None}, in which case a
        non-persistent L{HTTPConnectionPool} instance will be created.

    @ivar _contextFactory: A web context factory which will be used to create
        SSL context objects for any SSL connections the agent needs to make.

    @ivar _connectTimeout: If not C{None}, the timeout passed to C{connectTCP}
        or C{connectSSL} for specifying the connection timeout.

    @ivar _bindAddress: If not C{None}, the address passed to C{connectTCP} or
        C{connectSSL} for specifying the local address to bind to.

    @since: 9.0
    """

    def __init__(self, reactor, contextFactory=WebClientContextFactory(),
                 connectTimeout=None, bindAddress=None,
                 pool=None):
        _AgentBase.__init__(self, reactor, pool)
        self._contextFactory = contextFactory
        self._connectTimeout = connectTimeout
        self._bindAddress = bindAddress


    def _wrapContextFactory(self, host, port):
        """
        Create and return a normal context factory wrapped around
        C{self._contextFactory} in such a way that C{self._contextFactory} will
        have the host and port information passed to it.

        @param host: A C{str} giving the hostname which will be connected to in
            order to issue a request.

        @param port: An C{int} giving the port number the connection will be
            on.

        @return: A context factory suitable to be passed to
            C{reactor.connectSSL}.
        """
        return _WebToNormalContextFactory(self._contextFactory, host, port)


    def _getEndpoint(self, scheme, host, port):
        """
        Get an endpoint for the given host and port, using a transport
        selected based on scheme.

        @param scheme: A string like C{'http'} or C{'https'} (the only two
            supported values) to use to determine how to establish the
            connection.

        @param host: A C{str} giving the hostname which will be connected to in
            order to issue a request.

        @param port: An C{int} giving the port number the connection will be
            on.

        @return: An endpoint which can be used to connect to given address.
        """
        kwargs = {}
        if self._connectTimeout is not None:
            kwargs['timeout'] = self._connectTimeout
        kwargs['bindAddress'] = self._bindAddress
        if scheme == 'http':
            return TCP4ClientEndpoint(self._reactor, host, port, **kwargs)
        elif scheme == 'https':
            return SSL4ClientEndpoint(self._reactor, host, port,
                                      self._wrapContextFactory(host, port),
                                      **kwargs)
        else:
            raise SchemeNotSupported("Unsupported scheme: %r" % (scheme,))


    def request(self, method, uri, headers=None, bodyProducer=None):
        """
        Issue a new request.

        @param method: The request method to send.
        @type method: C{str}

        @param uri: The request URI send.
        @type uri: C{str}

        @param headers: The request headers to send.  If no I{Host} header is
            included, one will be added based on the request URI.
        @type headers: L{Headers}

        @param bodyProducer: An object which will produce the request body or,
            if the request body is to be empty, L{None}.
        @type bodyProducer: L{IBodyProducer} provider

        @return: A L{Deferred} which fires with the result of the request (a
            L{twisted.web.iweb.IResponse} provider), or fails if there is a
            problem setting up a connection over which to issue the request.
            It may also fail with L{SchemeNotSupported} if the scheme of the
            given URI is not supported.
        @rtype: L{Deferred}
        """
        parsedURI = _parse(uri)
        try:
            endpoint = self._getEndpoint(parsedURI.scheme, parsedURI.host,
                                         parsedURI.port)
        except SchemeNotSupported:
            return defer.fail(Failure())
        key = (parsedURI.scheme, parsedURI.host, parsedURI.port)
        return self._requestWithEndpoint(key, endpoint, method, parsedURI,
                                         headers, bodyProducer, parsedURI.path)



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
                                         _parse(uri), headers, bodyProducer,
                                         uri)



class _FakeUrllib2Request(object):
    """
    A fake C{urllib2.Request} object for C{cookielib} to work with.

    @see: U{http://docs.python.org/library/urllib2.html#request-objects}

    @type uri: C{str}
    @ivar uri: Request URI.

    @type headers: L{twisted.web.http_headers.Headers}
    @ivar headers: Request headers.

    @type type: C{str}
    @ivar type: The scheme of the URI.

    @type host: C{str}
    @ivar host: The host[:port] of the URI.

    @since: 11.1
    """
    def __init__(self, uri):
        self.uri = uri
        self.headers = Headers()
        self.type, rest = splittype(self.uri)
        self.host, rest = splithost(rest)


    def has_header(self, header):
        return self.headers.hasHeader(header)


    def add_unredirected_header(self, name, value):
        self.headers.addRawHeader(name, value)


    def get_full_url(self):
        return self.uri


    def get_header(self, name, default=None):
        headers = self.headers.getRawHeaders(name, default)
        if headers is not None:
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
                return self.response.headers.getRawHeaders(name, [])
        return _Meta()



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
        if not headers.hasHeader('cookie'):
            self.cookieJar.add_cookie_header(lastRequest)
            cookieHeader = lastRequest.get_header('Cookie', None)
            if cookieHeader is not None:
                headers = headers.copy()
                headers.addRawHeader('cookie', cookieHeader)

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
            raise ResponseFailed([failure.Failure()], self._response)
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
            raise ResponseFailed([reason, failure.Failure()], self._response)
        if rawData:
            self.original.dataReceived(rawData)
        self.original.connectionLost(reason)



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
        self._supported = ','.join([decoder[0] for decoder in decoders])


    def request(self, method, uri, headers=None, bodyProducer=None):
        """
        Send a client request which declares supporting compressed content.

        @see: L{Agent.request}.
        """
        if headers is None:
            headers = Headers()
        else:
            headers = headers.copy()
        headers.addRawHeader('accept-encoding', self._supported)
        deferred = self._agent.request(method, uri, headers, bodyProducer)
        return deferred.addCallback(self._handleResponse)


    def _handleResponse(self, response):
        """
        Check if the response is encoded, and wrap it to handle decompression.
        """
        contentEncodingHeaders = response.headers.getRawHeaders(
            'content-encoding', [])
        contentEncodingHeaders = ','.join(contentEncodingHeaders).split(',')
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
                'content-encoding', [','.join(contentEncodingHeaders)])
        else:
            response.headers.removeHeader('content-encoding')
        return response



class RedirectAgent(object):
    """
    An L{Agent} wrapper which handles HTTP redirects.

    The implementation is rather strict: 301 and 302 behaves like 307, not
    redirecting automatically on methods different from C{GET} and C{HEAD}.

    @param redirectLimit: The maximum number of times the agent is allowed to
        follow redirects before failing with a L{error.InfiniteRedirection}.

    @since: 11.1
    """

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


    def _handleRedirect(self, response, method, uri, headers, redirectCount):
        """
        Handle a redirect response, checking the number of redirects already
        followed, and extracting the location header fields.
        """
        if redirectCount >= self._redirectLimit:
            err = error.InfiniteRedirection(
                response.code,
                'Infinite redirection detected',
                location=uri)
            raise ResponseFailed([failure.Failure(err)], response)
        locationHeaders = response.headers.getRawHeaders('location', [])
        if not locationHeaders:
            err = error.RedirectWithNoLocation(
                response.code, 'No location header field', uri)
            raise ResponseFailed([failure.Failure(err)], response)
        location = locationHeaders[0]
        deferred = self._agent.request(method, location, headers)
        return deferred.addCallback(
            self._handleResponse, method, uri, headers, redirectCount + 1)


    def _handleResponse(self, response, method, uri, headers, redirectCount):
        """
        Handle the response, making another request if it indicates a redirect.
        """
        if response.code in (http.MOVED_PERMANENTLY, http.FOUND,
                             http.TEMPORARY_REDIRECT):
            if method not in ('GET', 'HEAD'):
                err = error.PageRedirect(response.code, location=uri)
                raise ResponseFailed([failure.Failure(err)], response)
            return self._handleRedirect(response, method, uri, headers,
                                        redirectCount)
        elif response.code == http.SEE_OTHER:
            return self._handleRedirect(response, 'GET', uri, headers,
                                        redirectCount)
        return response



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
    """
    d = defer.Deferred()
    response.deliverBody(_ReadBodyProtocol(response.code, response.phrase, d))
    return d



__all__ = [
    'PartialDownloadError', 'HTTPPageGetter', 'HTTPPageDownloader',
    'HTTPClientFactory', 'HTTPDownloader', 'getPage', 'downloadPage',
    'ResponseDone', 'Response', 'ResponseFailed', 'Agent', 'CookieAgent',
    'ProxyAgent', 'ContentDecoderAgent', 'GzipDecoder', 'RedirectAgent',
    'HTTPConnectionPool', 'readBody']
