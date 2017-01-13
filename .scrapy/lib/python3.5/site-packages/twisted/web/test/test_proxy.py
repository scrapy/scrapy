# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test for L{twisted.web.proxy}.
"""

from twisted.trial.unittest import TestCase
from twisted.test.proto_helpers import StringTransportWithDisconnection
from twisted.test.proto_helpers import MemoryReactor

from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.web.proxy import ReverseProxyResource, ProxyClientFactory
from twisted.web.proxy import ProxyClient, ProxyRequest, ReverseProxyRequest
from twisted.web.test.test_web import DummyRequest


class ReverseProxyResourceTests(TestCase):
    """
    Tests for L{ReverseProxyResource}.
    """

    def _testRender(self, uri, expectedURI):
        """
        Check that a request pointing at C{uri} produce a new proxy connection,
        with the path of this request pointing at C{expectedURI}.
        """
        root = Resource()
        reactor = MemoryReactor()
        resource = ReverseProxyResource(u"127.0.0.1", 1234, b"/path", reactor)
        root.putChild(b'index', resource)
        site = Site(root)

        transport = StringTransportWithDisconnection()
        channel = site.buildProtocol(None)
        channel.makeConnection(transport)
        # Clear the timeout if the tests failed
        self.addCleanup(channel.connectionLost, None)

        channel.dataReceived(b"GET " +
                             uri +
                             b" HTTP/1.1\r\nAccept: text/html\r\n\r\n")

        # Check that one connection has been created, to the good host/port
        self.assertEqual(len(reactor.tcpClients), 1)
        self.assertEqual(reactor.tcpClients[0][0], u"127.0.0.1")
        self.assertEqual(reactor.tcpClients[0][1], 1234)

        # Check the factory passed to the connect, and its given path
        factory = reactor.tcpClients[0][2]
        self.assertIsInstance(factory, ProxyClientFactory)
        self.assertEqual(factory.rest, expectedURI)
        self.assertEqual(factory.headers[b"host"], b"127.0.0.1:1234")


    def test_render(self):
        """
        Test that L{ReverseProxyResource.render} initiates a connection to the
        given server with a L{ProxyClientFactory} as parameter.
        """
        return self._testRender(b"/index", b"/path")


    def test_renderWithQuery(self):
        """
        Test that L{ReverseProxyResource.render} passes query parameters to the
        created factory.
        """
        return self._testRender(b"/index?foo=bar", b"/path?foo=bar")


    def test_getChild(self):
        """
        The L{ReverseProxyResource.getChild} method should return a resource
        instance with the same class as the originating resource, forward
        port, host, and reactor values, and update the path value with the
        value passed.
        """
        reactor = MemoryReactor()
        resource = ReverseProxyResource(u"127.0.0.1", 1234, b"/path", reactor)
        child = resource.getChild(b'foo', None)
        # The child should keep the same class
        self.assertIsInstance(child, ReverseProxyResource)
        self.assertEqual(child.path, b"/path/foo")
        self.assertEqual(child.port, 1234)
        self.assertEqual(child.host, u"127.0.0.1")
        self.assertIdentical(child.reactor, resource.reactor)


    def test_getChildWithSpecial(self):
        """
        The L{ReverseProxyResource} return by C{getChild} has a path which has
        already been quoted.
        """
        resource = ReverseProxyResource(u"127.0.0.1", 1234, b"/path")
        child = resource.getChild(b' /%', None)
        self.assertEqual(child.path, b"/path/%20%2F%25")



class DummyChannel(object):
    """
    A dummy HTTP channel, that does nothing but holds a transport and saves
    connection lost.

    @ivar transport: the transport used by the client.
    @ivar lostReason: the reason saved at connection lost.
    """

    def __init__(self, transport):
        """
        Hold a reference to the transport.
        """
        self.transport = transport
        self.lostReason = None


    def connectionLost(self, reason):
        """
        Keep track of the connection lost reason.
        """
        self.lostReason = reason


    def getPeer(self):
        """
        Get peer information from the transport.
        """
        return self.transport.getPeer()


    def getHost(self):
        """
        Get host information from the transport.
        """
        return self.transport.getHost()



class ProxyClientTests(TestCase):
    """
    Tests for L{ProxyClient}.
    """

    def _parseOutHeaders(self, content):
        """
        Parse the headers out of some web content.

        @param content: Bytes received from a web server.
        @return: A tuple of (requestLine, headers, body). C{headers} is a dict
            of headers, C{requestLine} is the first line (e.g. "POST /foo ...")
            and C{body} is whatever is left.
        """
        headers, body = content.split(b'\r\n\r\n')
        headers = headers.split(b'\r\n')
        requestLine = headers.pop(0)
        return (
            requestLine, dict(header.split(b': ') for header in headers), body)


    def makeRequest(self, path):
        """
        Make a dummy request object for the URL path.

        @param path: A URL path, beginning with a slash.
        @return: A L{DummyRequest}.
        """
        return DummyRequest(path)


    def makeProxyClient(self, request, method=b"GET", headers=None,
                        requestBody=b""):
        """
        Make a L{ProxyClient} object used for testing.

        @param request: The request to use.
        @param method: The HTTP method to use, GET by default.
        @param headers: The HTTP headers to use expressed as a dict. If not
            provided, defaults to {'accept': 'text/html'}.
        @param requestBody: The body of the request. Defaults to the empty
            string.
        @return: A L{ProxyClient}
        """
        if headers is None:
            headers = {b"accept": b"text/html"}
        path = b'/' + request.postpath
        return ProxyClient(
            method, path, b'HTTP/1.0', headers, requestBody, request)


    def connectProxy(self, proxyClient):
        """
        Connect a proxy client to a L{StringTransportWithDisconnection}.

        @param proxyClient: A L{ProxyClient}.
        @return: The L{StringTransportWithDisconnection}.
        """
        clientTransport = StringTransportWithDisconnection()
        clientTransport.protocol = proxyClient
        proxyClient.makeConnection(clientTransport)
        return clientTransport


    def assertForwardsHeaders(self, proxyClient, requestLine, headers):
        """
        Assert that C{proxyClient} sends C{headers} when it connects.

        @param proxyClient: A L{ProxyClient}.
        @param requestLine: The request line we expect to be sent.
        @param headers: A dict of headers we expect to be sent.
        @return: If the assertion is successful, return the request body as
            bytes.
        """
        self.connectProxy(proxyClient)
        requestContent = proxyClient.transport.value()
        receivedLine, receivedHeaders, body = self._parseOutHeaders(
            requestContent)
        self.assertEqual(receivedLine, requestLine)
        self.assertEqual(receivedHeaders, headers)
        return body


    def makeResponseBytes(self, code, message, headers, body):
        lines = [b"HTTP/1.0 " + str(code).encode('ascii') + b' ' + message]
        for header, values in headers:
            for value in values:
                lines.append(header + b': ' + value)
        lines.extend([b'', body])
        return b'\r\n'.join(lines)


    def assertForwardsResponse(self, request, code, message, headers, body):
        """
        Assert that C{request} has forwarded a response from the server.

        @param request: A L{DummyRequest}.
        @param code: The expected HTTP response code.
        @param message: The expected HTTP message.
        @param headers: The expected HTTP headers.
        @param body: The expected response body.
        """
        self.assertEqual(request.responseCode, code)
        self.assertEqual(request.responseMessage, message)
        receivedHeaders = list(request.responseHeaders.getAllRawHeaders())
        receivedHeaders.sort()
        expectedHeaders = headers[:]
        expectedHeaders.sort()
        self.assertEqual(receivedHeaders, expectedHeaders)
        self.assertEqual(b''.join(request.written), body)


    def _testDataForward(self, code, message, headers, body, method=b"GET",
                         requestBody=b"", loseConnection=True):
        """
        Build a fake proxy connection, and send C{data} over it, checking that
        it's forwarded to the originating request.
        """
        request = self.makeRequest(b'foo')
        client = self.makeProxyClient(
            request, method, {b'accept': b'text/html'}, requestBody)

        receivedBody = self.assertForwardsHeaders(
            client, method + b' /foo HTTP/1.0',
            {b'connection': b'close', b'accept': b'text/html'})

        self.assertEqual(receivedBody, requestBody)

        # Fake an answer
        client.dataReceived(
            self.makeResponseBytes(code, message, headers, body))

        # Check that the response data has been forwarded back to the original
        # requester.
        self.assertForwardsResponse(request, code, message, headers, body)

        # Check that when the response is done, the request is finished.
        if loseConnection:
            client.transport.loseConnection()

        # Even if we didn't call loseConnection, the transport should be
        # disconnected.  This lets us not rely on the server to close our
        # sockets for us.
        self.assertFalse(client.transport.connected)
        self.assertEqual(request.finished, 1)


    def test_forward(self):
        """
        When connected to the server, L{ProxyClient} should send the saved
        request, with modifications of the headers, and then forward the result
        to the parent request.
        """
        return self._testDataForward(
            200, b"OK", [(b"Foo", [b"bar", b"baz"])], b"Some data\r\n")


    def test_postData(self):
        """
        Try to post content in the request, and check that the proxy client
        forward the body of the request.
        """
        return self._testDataForward(
            200, b"OK", [(b"Foo", [b"bar"])], b"Some data\r\n", b"POST", b"Some content")


    def test_statusWithMessage(self):
        """
        If the response contains a status with a message, it should be
        forwarded to the parent request with all the information.
        """
        return self._testDataForward(
            404, b"Not Found", [], b"")


    def test_contentLength(self):
        """
        If the response contains a I{Content-Length} header, the inbound
        request object should still only have C{finish} called on it once.
        """
        data = b"foo bar baz"
        return self._testDataForward(
            200,
            b"OK",
            [(b"Content-Length", [str(len(data)).encode('ascii')])],
            data)


    def test_losesConnection(self):
        """
        If the response contains a I{Content-Length} header, the outgoing
        connection is closed when all response body data has been received.
        """
        data = b"foo bar baz"
        return self._testDataForward(
            200,
            b"OK",
            [(b"Content-Length", [str(len(data)).encode('ascii')])],
            data,
            loseConnection=False)


    def test_headersCleanups(self):
        """
        The headers given at initialization should be modified:
        B{proxy-connection} should be removed if present, and B{connection}
        should be added.
        """
        client = ProxyClient(b'GET', b'/foo', b'HTTP/1.0',
            {b"accept": b"text/html", b"proxy-connection": b"foo"}, b'', None)
        self.assertEqual(client.headers,
            {b"accept": b"text/html", b"connection": b"close"})


    def test_keepaliveNotForwarded(self):
        """
        The proxy doesn't really know what to do with keepalive things from
        the remote server, so we stomp over any keepalive header we get from
        the client.
        """
        headers = {
            b"accept": b"text/html",
            b'keep-alive': b'300',
            b'connection': b'keep-alive',
            }
        expectedHeaders = headers.copy()
        expectedHeaders[b'connection'] = b'close'
        del expectedHeaders[b'keep-alive']
        client = ProxyClient(b'GET', b'/foo', b'HTTP/1.0', headers, b'', None)
        self.assertForwardsHeaders(
            client, b'GET /foo HTTP/1.0', expectedHeaders)


    def test_defaultHeadersOverridden(self):
        """
        L{server.Request} within the proxy sets certain response headers by
        default. When we get these headers back from the remote server, the
        defaults are overridden rather than simply appended.
        """
        request = self.makeRequest(b'foo')
        request.responseHeaders.setRawHeaders(b'server', [b'old-bar'])
        request.responseHeaders.setRawHeaders(b'date', [b'old-baz'])
        request.responseHeaders.setRawHeaders(b'content-type', [b"old/qux"])
        client = self.makeProxyClient(request, headers={b'accept': b'text/html'})
        self.connectProxy(client)
        headers = {
            b'Server': [b'bar'],
            b'Date': [b'2010-01-01'],
            b'Content-Type': [b'application/x-baz'],
            }
        client.dataReceived(
            self.makeResponseBytes(200, b"OK", headers.items(), b''))
        self.assertForwardsResponse(
            request, 200, b'OK', list(headers.items()), b'')



class ProxyClientFactoryTests(TestCase):
    """
    Tests for L{ProxyClientFactory}.
    """

    def test_connectionFailed(self):
        """
        Check that L{ProxyClientFactory.clientConnectionFailed} produces
        a B{501} response to the parent request.
        """
        request = DummyRequest([b'foo'])
        factory = ProxyClientFactory(b'GET', b'/foo', b'HTTP/1.0',
                                     {b"accept": b"text/html"}, '', request)

        factory.clientConnectionFailed(None, None)
        self.assertEqual(request.responseCode, 501)
        self.assertEqual(request.responseMessage, b"Gateway error")
        self.assertEqual(
            list(request.responseHeaders.getAllRawHeaders()),
            [(b"Content-Type", [b"text/html"])])
        self.assertEqual(
            b''.join(request.written),
            b"<H1>Could not connect</H1>")
        self.assertEqual(request.finished, 1)


    def test_buildProtocol(self):
        """
        L{ProxyClientFactory.buildProtocol} should produce a L{ProxyClient}
        with the same values of attributes (with updates on the headers).
        """
        factory = ProxyClientFactory(b'GET', b'/foo', b'HTTP/1.0',
                                     {b"accept": b"text/html"}, b'Some data',
                                     None)
        proto = factory.buildProtocol(None)
        self.assertIsInstance(proto, ProxyClient)
        self.assertEqual(proto.command, b'GET')
        self.assertEqual(proto.rest, b'/foo')
        self.assertEqual(proto.data, b'Some data')
        self.assertEqual(proto.headers,
                          {b"accept": b"text/html", b"connection": b"close"})



class ProxyRequestTests(TestCase):
    """
    Tests for L{ProxyRequest}.
    """

    def _testProcess(self, uri, expectedURI, method=b"GET", data=b""):
        """
        Build a request pointing at C{uri}, and check that a proxied request
        is created, pointing a C{expectedURI}.
        """
        transport = StringTransportWithDisconnection()
        channel = DummyChannel(transport)
        reactor = MemoryReactor()
        request = ProxyRequest(channel, False, reactor)
        request.gotLength(len(data))
        request.handleContentChunk(data)
        request.requestReceived(method, b'http://example.com' + uri,
                                b'HTTP/1.0')

        self.assertEqual(len(reactor.tcpClients), 1)
        self.assertEqual(reactor.tcpClients[0][0], u"example.com")
        self.assertEqual(reactor.tcpClients[0][1], 80)

        factory = reactor.tcpClients[0][2]
        self.assertIsInstance(factory, ProxyClientFactory)
        self.assertEqual(factory.command, method)
        self.assertEqual(factory.version, b'HTTP/1.0')
        self.assertEqual(factory.headers, {b'host': b'example.com'})
        self.assertEqual(factory.data, data)
        self.assertEqual(factory.rest, expectedURI)
        self.assertEqual(factory.father, request)


    def test_process(self):
        """
        L{ProxyRequest.process} should create a connection to the given server,
        with a L{ProxyClientFactory} as connection factory, with the correct
        parameters:
            - forward comment, version and data values
            - update headers with the B{host} value
            - remove the host from the URL
            - pass the request as parent request
        """
        return self._testProcess(b"/foo/bar", b"/foo/bar")


    def test_processWithoutTrailingSlash(self):
        """
        If the incoming request doesn't contain a slash,
        L{ProxyRequest.process} should add one when instantiating
        L{ProxyClientFactory}.
        """
        return self._testProcess(b"", b"/")


    def test_processWithData(self):
        """
        L{ProxyRequest.process} should be able to retrieve request body and
        to forward it.
        """
        return self._testProcess(
            b"/foo/bar", b"/foo/bar", b"POST", b"Some content")


    def test_processWithPort(self):
        """
        Check that L{ProxyRequest.process} correctly parse port in the incoming
        URL, and create an outgoing connection with this port.
        """
        transport = StringTransportWithDisconnection()
        channel = DummyChannel(transport)
        reactor = MemoryReactor()
        request = ProxyRequest(channel, False, reactor)
        request.gotLength(0)
        request.requestReceived(b'GET', b'http://example.com:1234/foo/bar',
                                b'HTTP/1.0')

        # That should create one connection, with the port parsed from the URL
        self.assertEqual(len(reactor.tcpClients), 1)
        self.assertEqual(reactor.tcpClients[0][0], u"example.com")
        self.assertEqual(reactor.tcpClients[0][1], 1234)



class DummyFactory(object):
    """
    A simple holder for C{host} and C{port} information.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port



class ReverseProxyRequestTests(TestCase):
    """
    Tests for L{ReverseProxyRequest}.
    """

    def test_process(self):
        """
        L{ReverseProxyRequest.process} should create a connection to its
        factory host/port, using a L{ProxyClientFactory} instantiated with the
        correct parameters, and particularly set the B{host} header to the
        factory host.
        """
        transport = StringTransportWithDisconnection()
        channel = DummyChannel(transport)
        reactor = MemoryReactor()
        request = ReverseProxyRequest(channel, False, reactor)
        request.factory = DummyFactory(u"example.com", 1234)
        request.gotLength(0)
        request.requestReceived(b'GET', b'/foo/bar', b'HTTP/1.0')

        # Check that one connection has been created, to the good host/port
        self.assertEqual(len(reactor.tcpClients), 1)
        self.assertEqual(reactor.tcpClients[0][0], u"example.com")
        self.assertEqual(reactor.tcpClients[0][1], 1234)

        # Check the factory passed to the connect, and its headers
        factory = reactor.tcpClients[0][2]
        self.assertIsInstance(factory, ProxyClientFactory)
        self.assertEqual(factory.headers, {b'host': b'example.com'})
