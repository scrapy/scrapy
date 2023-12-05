# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test HTTP support.
"""


import base64
import calendar
import random
from io import BytesIO
from itertools import cycle
from typing import Sequence, Union
from unittest import skipIf
from urllib.parse import clear_cache  # type: ignore[attr-defined]
from urllib.parse import urlparse, urlunsplit

from zope.interface import directlyProvides, providedBy, provider
from zope.interface.verify import verifyObject

import hamcrest

from twisted.internet import address
from twisted.internet.error import ConnectionDone, ConnectionLost
from twisted.internet.task import Clock
from twisted.logger import globalLogPublisher
from twisted.protocols import loopback
from twisted.python.compat import iterbytes, networkString
from twisted.python.components import proxyForInterface
from twisted.python.failure import Failure
from twisted.test.proto_helpers import (
    EventLoggingObserver,
    NonStreamingProducer,
    StringTransport,
)
from twisted.test.test_internet import DummyProducer
from twisted.trial import unittest
from twisted.trial.unittest import TestCase
from twisted.web import http, http_headers, iweb
from twisted.web.http import PotentialDataLoss, _DataLoss, _IdentityTransferDecoder
from twisted.web.test.requesthelper import (
    DummyChannel,
    bytesLinearWhitespaceComponents,
    sanitizedBytes,
    textLinearWhitespaceComponents,
)
from ._util import assertIsFilesystemTemporary


class _IDeprecatedHTTPChannelToRequestInterfaceProxy(
    proxyForInterface(  # type: ignore[misc]
        http._IDeprecatedHTTPChannelToRequestInterface
    )
):
    """
    Proxy L{_IDeprecatedHTTPChannelToRequestInterface}.  Used to
    assert that the interface matches what L{HTTPChannel} expects.
    """


def _makeRequestProxyFactory(clsToWrap):
    """
    Return a callable that proxies instances of C{clsToWrap} via
        L{_IDeprecatedHTTPChannelToRequestInterface}.

    @param clsToWrap: The class whose instances will be proxied.
    @type cls: L{_IDeprecatedHTTPChannelToRequestInterface}
        implementer.

    @return: A factory that returns
        L{_IDeprecatedHTTPChannelToRequestInterface} proxies.
    @rtype: L{callable} whose interface matches C{clsToWrap}'s constructor.
    """

    def _makeRequestProxy(*args, **kwargs):
        instance = clsToWrap(*args, **kwargs)
        return _IDeprecatedHTTPChannelToRequestInterfaceProxy(instance)

    # For INonQueuedRequestFactory
    directlyProvides(_makeRequestProxy, providedBy(clsToWrap))
    return _makeRequestProxy


class DummyPullProducerHandler(http.Request):
    """
    An HTTP request handler that registers a dummy pull producer to serve the
    body.

    The owner must call C{finish} to complete the response.
    """

    def process(self):
        self._actualProducer = NonStreamingProducer(self)
        self.setResponseCode(200)
        self.registerProducer(self._actualProducer, False)


DummyPullProducerHandlerProxy = _makeRequestProxyFactory(DummyPullProducerHandler)


class DateTimeTests(unittest.TestCase):
    """Test date parsing functions."""

    def testRoundtrip(self):
        for i in range(10000):
            time = random.randint(0, 2000000000)
            timestr = http.datetimeToString(time)
            time2 = http.stringToDatetime(timestr)
            self.assertEqual(time, time2)

    def testStringToDatetime(self):
        dateStrings = [
            b"Sun, 06 Nov 1994 08:49:37 GMT",
            b"06 Nov 1994 08:49:37 GMT",
            b"Sunday, 06-Nov-94 08:49:37 GMT",
            b"06-Nov-94 08:49:37 GMT",
            b"Sunday, 06-Nov-1994 08:49:37 GMT",
            b"06-Nov-1994 08:49:37 GMT",
            b"Sun Nov  6 08:49:37 1994",
            b"Nov  6 08:49:37 1994",
        ]
        dateInt = calendar.timegm((1994, 11, 6, 8, 49, 37, 6, 6, 0))
        for dateString in dateStrings:
            self.assertEqual(http.stringToDatetime(dateString), dateInt)
        self.assertEqual(
            http.stringToDatetime(b"Thursday, 29-Sep-16 17:15:29 GMT"),
            calendar.timegm((2016, 9, 29, 17, 15, 29, 3, 273, 0)),
        )


class DummyHTTPHandler(http.Request):
    def process(self):
        self.content.seek(0, 0)
        data = self.content.read()
        length = self.getHeader(b"content-length")
        if length is None:
            length = networkString(str(length))
        request = b"'''\n" + length + b"\n" + data + b"'''\n"
        self.setResponseCode(200)
        self.setHeader(b"Request", self.uri)
        self.setHeader(b"Command", self.method)
        self.setHeader(b"Version", self.clientproto)
        self.setHeader(b"Content-Length", b"%d" % (len(request),))
        self.write(request)
        self.finish()


DummyHTTPHandlerProxy = _makeRequestProxyFactory(DummyHTTPHandler)


@provider(iweb.INonQueuedRequestFactory)
class DummyNewHTTPHandler(DummyHTTPHandler):
    """
    This is exactly like the DummyHTTPHandler but it takes only one argument
    in its constructor, with no default arguments. This exists to test an
    alternative code path in L{HTTPChannel}.
    """

    def __init__(self, channel):
        DummyHTTPHandler.__init__(self, channel)


DummyNewHTTPHandlerProxy = _makeRequestProxyFactory(DummyNewHTTPHandler)


class DelayedHTTPHandler(DummyHTTPHandler):
    """
    Like L{DummyHTTPHandler}, but doesn't respond immediately.
    """

    def process(self):
        pass

    def delayedProcess(self):
        DummyHTTPHandler.process(self)


DelayedHTTPHandlerProxy = _makeRequestProxyFactory(DelayedHTTPHandler)


class LoopbackHTTPClient(http.HTTPClient):
    def connectionMade(self):
        self.sendCommand(b"GET", b"/foo/bar")
        self.sendHeader(b"Content-Length", 10)
        self.endHeaders()
        self.transport.write(b"0123456789")


def parametrizeTimeoutMixin(protocol, reactor):
    """
    Parametrizes the L{TimeoutMixin} so that it works with whatever reactor is
    being used by the test.

    @param protocol: A L{_GenericHTTPChannel} or something implementing a
        similar interface.
    @type protocol: L{_GenericHTTPChannel}

    @param reactor: An L{IReactorTime} implementation.
    @type reactor: L{IReactorTime}

    @return: The C{channel}, with its C{callLater} method patched.
    """
    # This is a terrible violation of the abstraction later of
    # _genericHTTPChannelProtocol, but we need to do it because
    # policies.TimeoutMixin doesn't accept a reactor on the object.
    # See https://twistedmatrix.com/trac/ticket/8488
    protocol._channel.callLater = reactor.callLater
    return protocol


class ResponseTestMixin:
    """
    A mixin that provides a simple means of comparing an actual response string
    to an expected response string by performing the minimal parsing.
    """

    def assertResponseEquals(self, responses, expected):
        """
        Assert that the C{responses} matches the C{expected} responses.

        @type responses: C{bytes}
        @param responses: The bytes sent in response to one or more requests.

        @type expected: C{list} of C{tuple} of C{bytes}
        @param expected: The expected values for the responses.  Each tuple
            element of the list represents one response.  Each byte string
            element of the tuple is a full header line without delimiter, except
            for the last element which gives the full response body.
        """
        for response in expected:
            expectedHeaders, expectedContent = response[:-1], response[-1]
            # Intentionally avoid mutating the inputs here.
            expectedStatus = expectedHeaders[0]
            expectedHeaders = expectedHeaders[1:]

            headers, rest = responses.split(b"\r\n\r\n", 1)
            headers = headers.splitlines()
            status = headers.pop(0)

            self.assertEqual(expectedStatus, status)
            self.assertEqual(set(headers), set(expectedHeaders))
            content = rest[: len(expectedContent)]
            responses = rest[len(expectedContent) :]
            self.assertEqual(content, expectedContent)


class HTTP1_0Tests(unittest.TestCase, ResponseTestMixin):
    requests = (
        b"GET / HTTP/1.0\r\n"
        b"\r\n"
        b"GET / HTTP/1.1\r\n"
        b"Accept: text/html\r\n"
        b"\r\n"
    )

    expected_response: Union[Sequence[Sequence[bytes]], bytes] = [
        (
            b"HTTP/1.0 200 OK",
            b"Request: /",
            b"Command: GET",
            b"Version: HTTP/1.0",
            b"Content-Length: 13",
            b"'''\nNone\n'''\n",
        )
    ]

    def test_buffer(self):
        """
        Send requests over a channel and check responses match what is expected.
        """
        b = StringTransport()
        a = http.HTTPChannel()
        a.requestFactory = DummyHTTPHandlerProxy
        a.makeConnection(b)
        # one byte at a time, to stress it.
        for byte in iterbytes(self.requests):
            a.dataReceived(byte)
        a.connectionLost(IOError("all one"))
        value = b.value()
        self.assertResponseEquals(value, self.expected_response)

    def test_requestBodyTimeout(self):
        """
        L{HTTPChannel} resets its timeout whenever data from a request body is
        delivered to it.
        """
        clock = Clock()
        transport = StringTransport()
        protocol = http.HTTPChannel()
        protocol.timeOut = 100
        protocol.callLater = clock.callLater
        protocol.makeConnection(transport)
        protocol.dataReceived(b"POST / HTTP/1.0\r\nContent-Length: 2\r\n\r\n")
        clock.advance(99)
        self.assertFalse(transport.disconnecting)
        protocol.dataReceived(b"x")
        clock.advance(99)
        self.assertFalse(transport.disconnecting)
        protocol.dataReceived(b"x")
        self.assertEqual(len(protocol.requests), 1)

    def test_requestBodyDefaultTimeout(self):
        """
        L{HTTPChannel}'s default timeout is 60 seconds.
        """
        clock = Clock()
        transport = StringTransport()
        factory = http.HTTPFactory()
        protocol = factory.buildProtocol(None)
        protocol = parametrizeTimeoutMixin(protocol, clock)
        protocol.makeConnection(transport)
        protocol.dataReceived(b"POST / HTTP/1.0\r\nContent-Length: 2\r\n\r\n")
        clock.advance(59)
        self.assertFalse(transport.disconnecting)
        clock.advance(1)
        self.assertTrue(transport.disconnecting)

    def test_transportForciblyClosed(self):
        """
        If a timed out transport doesn't close after 15 seconds, the
        L{HTTPChannel} will forcibly close it.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)
        clock = Clock()
        transport = StringTransport()
        factory = http.HTTPFactory()
        protocol = factory.buildProtocol(None)
        protocol = parametrizeTimeoutMixin(protocol, clock)
        protocol.makeConnection(transport)
        protocol.dataReceived(b"POST / HTTP/1.0\r\nContent-Length: 2\r\n\r\n")
        self.assertFalse(transport.disconnecting)
        self.assertFalse(transport.disconnected)

        # Force the initial timeout.
        clock.advance(60)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)
        self.assertEquals(1, len(logObserver))
        event = logObserver[0]
        self.assertIn("Timing out client: {peer}", event["log_format"])

        # Watch the transport get force-closed.
        clock.advance(14)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)
        clock.advance(1)
        self.assertTrue(transport.disconnecting)
        self.assertTrue(transport.disconnected)
        self.assertEquals(2, len(logObserver))
        event = logObserver[1]
        self.assertEquals("Forcibly timing out client: {peer}", event["log_format"])

    def test_transportNotAbortedAfterConnectionLost(self):
        """
        If a timed out transport ends up calling C{connectionLost}, it prevents
        the force-closure of the transport.
        """
        clock = Clock()
        transport = StringTransport()
        factory = http.HTTPFactory()
        protocol = factory.buildProtocol(None)
        protocol = parametrizeTimeoutMixin(protocol, clock)
        protocol.makeConnection(transport)
        protocol.dataReceived(b"POST / HTTP/1.0\r\nContent-Length: 2\r\n\r\n")
        self.assertFalse(transport.disconnecting)
        self.assertFalse(transport.disconnected)

        # Force the initial timeout.
        clock.advance(60)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)

        # Move forward nearly to the timeout, then fire connectionLost.
        clock.advance(14)
        protocol.connectionLost(None)

        # Check that the transport isn't forcibly closed.
        clock.advance(1)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)

    def test_transportNotAbortedWithZeroAbortTimeout(self):
        """
        If the L{HTTPChannel} has its c{abortTimeout} set to L{None}, it never
        aborts.
        """
        clock = Clock()
        transport = StringTransport()
        factory = http.HTTPFactory()
        protocol = factory.buildProtocol(None)
        protocol._channel.abortTimeout = None
        protocol = parametrizeTimeoutMixin(protocol, clock)
        protocol.makeConnection(transport)
        protocol.dataReceived(b"POST / HTTP/1.0\r\nContent-Length: 2\r\n\r\n")
        self.assertFalse(transport.disconnecting)
        self.assertFalse(transport.disconnected)

        # Force the initial timeout.
        clock.advance(60)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)

        # Move an absurdly long way just to prove the point.
        clock.advance(2 ** 32)
        self.assertTrue(transport.disconnecting)
        self.assertFalse(transport.disconnected)

    def test_connectionLostAfterForceClose(self):
        """
        If a timed out transport doesn't close after 15 seconds, the
        L{HTTPChannel} will forcibly close it.
        """
        clock = Clock()
        transport = StringTransport()
        factory = http.HTTPFactory()
        protocol = factory.buildProtocol(None)
        protocol = parametrizeTimeoutMixin(protocol, clock)
        protocol.makeConnection(transport)
        protocol.dataReceived(b"POST / HTTP/1.0\r\nContent-Length: 2\r\n\r\n")
        self.assertFalse(transport.disconnecting)
        self.assertFalse(transport.disconnected)

        # Force the initial timeout and the follow-on forced closure.
        clock.advance(60)
        clock.advance(15)
        self.assertTrue(transport.disconnecting)
        self.assertTrue(transport.disconnected)

        # Now call connectionLost on the protocol. This is done by some
        # transports, including TCP and TLS. We don't have anything we can
        # assert on here: this just must not explode.
        protocol.connectionLost(ConnectionDone)

    def test_noPipeliningApi(self):
        """
        Test that a L{http.Request} subclass with no queued kwarg works as
        expected.
        """
        b = StringTransport()
        a = http.HTTPChannel()
        a.requestFactory = DummyHTTPHandlerProxy
        a.makeConnection(b)
        # one byte at a time, to stress it.
        for byte in iterbytes(self.requests):
            a.dataReceived(byte)
        a.connectionLost(IOError("all done"))
        value = b.value()
        self.assertResponseEquals(value, self.expected_response)

    def test_noPipelining(self):
        """
        Test that pipelined requests get buffered, not processed in parallel.
        """
        b = StringTransport()
        a = http.HTTPChannel()
        a.requestFactory = DelayedHTTPHandlerProxy
        a.makeConnection(b)
        # one byte at a time, to stress it.
        for byte in iterbytes(self.requests):
            a.dataReceived(byte)
        value = b.value()

        # So far only one request should have been dispatched.
        self.assertEqual(value, b"")
        self.assertEqual(1, len(a.requests))

        # Now, process each request one at a time.
        while a.requests:
            self.assertEqual(1, len(a.requests))
            request = a.requests[0].original
            request.delayedProcess()

        value = b.value()
        self.assertResponseEquals(value, self.expected_response)


class HTTP1_1Tests(HTTP1_0Tests):

    requests = (
        b"GET / HTTP/1.1\r\n"
        b"Accept: text/html\r\n"
        b"\r\n"
        b"POST / HTTP/1.1\r\n"
        b"Content-Length: 10\r\n"
        b"\r\n"
        b"0123456789POST / HTTP/1.1\r\n"
        b"Content-Length: 10\r\n"
        b"\r\n"
        b"0123456789HEAD / HTTP/1.1\r\n"
        b"\r\n"
    )

    expected_response = [
        (
            b"HTTP/1.1 200 OK",
            b"Request: /",
            b"Command: GET",
            b"Version: HTTP/1.1",
            b"Content-Length: 13",
            b"'''\nNone\n'''\n",
        ),
        (
            b"HTTP/1.1 200 OK",
            b"Request: /",
            b"Command: POST",
            b"Version: HTTP/1.1",
            b"Content-Length: 21",
            b"'''\n10\n0123456789'''\n",
        ),
        (
            b"HTTP/1.1 200 OK",
            b"Request: /",
            b"Command: POST",
            b"Version: HTTP/1.1",
            b"Content-Length: 21",
            b"'''\n10\n0123456789'''\n",
        ),
        (
            b"HTTP/1.1 200 OK",
            b"Request: /",
            b"Command: HEAD",
            b"Version: HTTP/1.1",
            b"Content-Length: 13",
            b"",
        ),
    ]


class HTTP1_1_close_Tests(HTTP1_0Tests):

    requests = (
        b"GET / HTTP/1.1\r\n"
        b"Accept: text/html\r\n"
        b"Connection: close\r\n"
        b"\r\n"
        b"GET / HTTP/1.0\r\n"
        b"\r\n"
    )

    expected_response = [
        (
            b"HTTP/1.1 200 OK",
            b"Connection: close",
            b"Request: /",
            b"Command: GET",
            b"Version: HTTP/1.1",
            b"Content-Length: 13",
            b"'''\nNone\n'''\n",
        )
    ]


class HTTP0_9Tests(HTTP1_0Tests):

    requests = b"GET /\r\n"

    expected_response = b"HTTP/1.1 400 Bad Request\r\n\r\n"

    def assertResponseEquals(self, response, expectedResponse):
        self.assertEqual(response, expectedResponse)

    def test_noPipelining(self):
        raise unittest.SkipTest("HTTP/0.9 not supported")


class PipeliningBodyTests(unittest.TestCase, ResponseTestMixin):
    """
    Tests that multiple pipelined requests with bodies are correctly buffered.
    """

    requests = (
        b"POST / HTTP/1.1\r\n"
        b"Content-Length: 10\r\n"
        b"\r\n"
        b"0123456789POST / HTTP/1.1\r\n"
        b"Content-Length: 10\r\n"
        b"\r\n"
        b"0123456789"
    )

    expectedResponses = [
        (
            b"HTTP/1.1 200 OK",
            b"Request: /",
            b"Command: POST",
            b"Version: HTTP/1.1",
            b"Content-Length: 21",
            b"'''\n10\n0123456789'''\n",
        ),
        (
            b"HTTP/1.1 200 OK",
            b"Request: /",
            b"Command: POST",
            b"Version: HTTP/1.1",
            b"Content-Length: 21",
            b"'''\n10\n0123456789'''\n",
        ),
    ]

    def test_noPipelining(self):
        """
        Test that pipelined requests get buffered, not processed in parallel.
        """
        b = StringTransport()
        a = http.HTTPChannel()
        a.requestFactory = DelayedHTTPHandlerProxy
        a.makeConnection(b)
        # one byte at a time, to stress it.
        for byte in iterbytes(self.requests):
            a.dataReceived(byte)
        value = b.value()

        # So far only one request should have been dispatched.
        self.assertEqual(value, b"")
        self.assertEqual(1, len(a.requests))

        # Now, process each request one at a time.
        while a.requests:
            self.assertEqual(1, len(a.requests))
            request = a.requests[0].original
            request.delayedProcess()

        value = b.value()
        self.assertResponseEquals(value, self.expectedResponses)

    def test_pipeliningReadLimit(self):
        """
        When pipelined requests are received, we will optimistically continue
        receiving data up to a specified limit, then pause the transport.

        @see: L{http.HTTPChannel._optimisticEagerReadSize}
        """
        b = StringTransport()
        a = http.HTTPChannel()
        a.requestFactory = DelayedHTTPHandlerProxy
        a.makeConnection(b)
        underLimit = a._optimisticEagerReadSize // len(self.requests)
        for x in range(1, underLimit + 1):
            a.dataReceived(self.requests)
            self.assertEqual(
                b.producerState,
                "producing",
                "state was {state!r} after {x} iterations".format(
                    state=b.producerState, x=x
                ),
            )
        a.dataReceived(self.requests)
        self.assertEquals(b.producerState, "paused")


class ShutdownTests(unittest.TestCase):
    """
    Tests that connections can be shut down by L{http.Request} objects.
    """

    class ShutdownHTTPHandler(http.Request):
        """
        A HTTP handler that just immediately calls loseConnection.
        """

        def process(self):
            self.loseConnection()

    request = b"POST / HTTP/1.1\r\n" b"Content-Length: 10\r\n" b"\r\n" b"0123456789"

    def test_losingConnection(self):
        """
        Calling L{http.Request.loseConnection} causes the transport to be
        disconnected.
        """
        b = StringTransport()
        a = http.HTTPChannel()
        a.requestFactory = _makeRequestProxyFactory(self.ShutdownHTTPHandler)
        a.makeConnection(b)
        a.dataReceived(self.request)

        # The transport should have been shut down.
        self.assertTrue(b.disconnecting)

        # No response should have been written.
        value = b.value()
        self.assertEqual(value, b"")


class SecurityTests(unittest.TestCase):
    """
    Tests that L{http.Request.isSecure} correctly takes the transport into
    account.
    """

    def test_isSecure(self):
        """
        Calling L{http.Request.isSecure} when the channel is backed with a
        secure transport will return L{True}.
        """
        b = DummyChannel.SSL()
        a = http.HTTPChannel()
        a.makeConnection(b)
        req = http.Request(a)
        self.assertTrue(req.isSecure())

    def test_notSecure(self):
        """
        Calling L{http.Request.isSecure} when the channel is not backed with a
        secure transport will return L{False}.
        """
        b = DummyChannel.TCP()
        a = http.HTTPChannel()
        a.makeConnection(b)
        req = http.Request(a)
        self.assertFalse(req.isSecure())

    def test_notSecureAfterFinish(self):
        """
        After a request is finished, calling L{http.Request.isSecure} will
        always return L{False}.
        """
        b = DummyChannel.SSL()
        a = http.HTTPChannel()
        a.makeConnection(b)
        req = http.Request(a)
        a.requests.append(req)

        req.setResponseCode(200)
        req.finish()
        self.assertFalse(req.isSecure())


class GenericHTTPChannelTests(unittest.TestCase):
    """
    Tests for L{http._genericHTTPChannelProtocol}, a L{HTTPChannel}-alike which
    can handle different HTTP protocol channels.
    """

    requests = (
        b"GET / HTTP/1.1\r\n"
        b"Accept: text/html\r\n"
        b"Connection: close\r\n"
        b"\r\n"
        b"GET / HTTP/1.0\r\n"
        b"\r\n"
    )

    def _negotiatedProtocolForTransportInstance(self, t):
        """
        Run a request using the specific instance of a transport. Returns the
        negotiated protocol string.
        """
        a = http._genericHTTPChannelProtocolFactory(b"")
        a.requestFactory = DummyHTTPHandlerProxy
        a.makeConnection(t)
        # one byte at a time, to stress it.
        for byte in iterbytes(self.requests):
            a.dataReceived(byte)
        a.connectionLost(IOError("all done"))
        return a._negotiatedProtocol

    @skipIf(not http.H2_ENABLED, "HTTP/2 support not present")
    def test_h2CancelsH11Timeout(self):
        """
        When the transport is switched to H2, the HTTPChannel timeouts are
        cancelled.
        """
        clock = Clock()

        a = http._genericHTTPChannelProtocolFactory(b"")
        a.requestFactory = DummyHTTPHandlerProxy

        # Set the original timeout to be 100s
        a.timeOut = 100
        a.callLater = clock.callLater

        b = StringTransport()
        b.negotiatedProtocol = b"h2"
        a.makeConnection(b)

        # We've made the connection, but we actually check if we've negotiated
        # H2 when data arrives. Right now, the HTTPChannel will have set up a
        # single delayed call.
        hamcrest.assert_that(
            clock.getDelayedCalls(),
            hamcrest.contains(
                hamcrest.has_property(
                    "cancelled",
                    hamcrest.equal_to(False),
                ),
            ),
        )
        h11Timeout = clock.getDelayedCalls()[0]

        # We give it the HTTP data, and it switches out for H2.
        a.dataReceived(b"")
        self.assertEqual(a._negotiatedProtocol, b"h2")

        # The first delayed call is cancelled, and H2 creates a new one for its
        # own timeouts.
        self.assertTrue(h11Timeout.cancelled)
        hamcrest.assert_that(
            clock.getDelayedCalls(),
            hamcrest.contains(
                hamcrest.has_property(
                    "cancelled",
                    hamcrest.equal_to(False),
                ),
            ),
        )

    def test_protocolUnspecified(self):
        """
        If the transport has no support for protocol negotiation (no
        negotiatedProtocol attribute), HTTP/1.1 is assumed.
        """
        b = StringTransport()
        negotiatedProtocol = self._negotiatedProtocolForTransportInstance(b)
        self.assertEqual(negotiatedProtocol, b"http/1.1")

    def test_protocolNone(self):
        """
        If the transport has no support for protocol negotiation (returns None
        for negotiatedProtocol), HTTP/1.1 is assumed.
        """
        b = StringTransport()
        b.negotiatedProtocol = None
        negotiatedProtocol = self._negotiatedProtocolForTransportInstance(b)
        self.assertEqual(negotiatedProtocol, b"http/1.1")

    def test_http11(self):
        """
        If the transport reports that HTTP/1.1 is negotiated, that's what's
        negotiated.
        """
        b = StringTransport()
        b.negotiatedProtocol = b"http/1.1"
        negotiatedProtocol = self._negotiatedProtocolForTransportInstance(b)
        self.assertEqual(negotiatedProtocol, b"http/1.1")

    @skipIf(not http.H2_ENABLED, "HTTP/2 support not present")
    def test_http2_present(self):
        """
        If the transport reports that HTTP/2 is negotiated and HTTP/2 is
        present, that's what's negotiated.
        """
        b = StringTransport()
        b.negotiatedProtocol = b"h2"
        negotiatedProtocol = self._negotiatedProtocolForTransportInstance(b)
        self.assertEqual(negotiatedProtocol, b"h2")

    @skipIf(http.H2_ENABLED, "HTTP/2 support present")
    def test_http2_absent(self):
        """
        If the transport reports that HTTP/2 is negotiated and HTTP/2 is not
        present, an error is encountered.
        """
        b = StringTransport()
        b.negotiatedProtocol = b"h2"
        self.assertRaises(
            ValueError,
            self._negotiatedProtocolForTransportInstance,
            b,
        )

    def test_unknownProtocol(self):
        """
        If the transport reports that a protocol other than HTTP/1.1 or HTTP/2
        is negotiated, an error occurs.
        """
        b = StringTransport()
        b.negotiatedProtocol = b"smtp"
        self.assertRaises(
            AssertionError,
            self._negotiatedProtocolForTransportInstance,
            b,
        )

    def test_factory(self):
        """
        The C{factory} attribute is taken from the inner channel.
        """
        a = http._genericHTTPChannelProtocolFactory(b"")
        a._channel.factory = b"Foo"
        self.assertEqual(a.factory, b"Foo")

    def test_GenericHTTPChannelPropagatesCallLater(self):
        """
        If C{callLater} is patched onto the L{http._GenericHTTPChannelProtocol}
        then we need to propagate it through to the backing channel.
        """
        clock = Clock()
        factory = http.HTTPFactory(reactor=clock)
        protocol = factory.buildProtocol(None)

        self.assertEqual(protocol.callLater, clock.callLater)
        self.assertEqual(protocol._channel.callLater, clock.callLater)

    @skipIf(not http.H2_ENABLED, "HTTP/2 support not present")
    def test_genericHTTPChannelCallLaterUpgrade(self):
        """
        If C{callLater} is patched onto the L{http._GenericHTTPChannelProtocol}
        then we need to propagate it across onto a new backing channel after
        upgrade.
        """
        clock = Clock()
        factory = http.HTTPFactory(reactor=clock)
        protocol = factory.buildProtocol(None)

        self.assertEqual(protocol.callLater, clock.callLater)
        self.assertEqual(protocol._channel.callLater, clock.callLater)

        transport = StringTransport()
        transport.negotiatedProtocol = b"h2"
        protocol.requestFactory = DummyHTTPHandler
        protocol.makeConnection(transport)

        # Send a byte to make it think the handshake is done.
        protocol.dataReceived(b"P")

        self.assertEqual(protocol.callLater, clock.callLater)
        self.assertEqual(protocol._channel.callLater, clock.callLater)

    @skipIf(not http.H2_ENABLED, "HTTP/2 support not present")
    def test_unregistersProducer(self):
        """
        The L{_GenericHTTPChannelProtocol} will unregister its proxy channel
        from the transport if upgrade is negotiated.
        """
        transport = StringTransport()
        transport.negotiatedProtocol = b"h2"

        genericProtocol = http._genericHTTPChannelProtocolFactory(b"")
        genericProtocol.requestFactory = DummyHTTPHandlerProxy
        genericProtocol.makeConnection(transport)

        originalChannel = genericProtocol._channel

        # We expect the transport has a underlying channel registered as
        # a producer.
        self.assertIs(transport.producer, originalChannel)

        # Force the upgrade.
        genericProtocol.dataReceived(b"P")

        # The transport should not have the original channel as its
        # producer...
        self.assertIsNot(transport.producer, originalChannel)

        # ...it should have the new H2 channel as its producer
        self.assertIs(transport.producer, genericProtocol._channel)


class HTTPLoopbackTests(unittest.TestCase):

    expectedHeaders = {
        b"request": b"/foo/bar",
        b"command": b"GET",
        b"version": b"HTTP/1.0",
        b"content-length": b"21",
    }
    numHeaders = 0
    gotStatus = 0
    gotResponse = 0
    gotEndHeaders = 0

    def _handleStatus(self, version, status, message):
        self.gotStatus = 1
        self.assertEqual(version, b"HTTP/1.0")
        self.assertEqual(status, b"200")

    def _handleResponse(self, data):
        self.gotResponse = 1
        self.assertEqual(data, b"'''\n10\n0123456789'''\n")

    def _handleHeader(self, key, value):
        self.numHeaders = self.numHeaders + 1
        self.assertEqual(self.expectedHeaders[key.lower()], value)

    def _handleEndHeaders(self):
        self.gotEndHeaders = 1
        self.assertEqual(self.numHeaders, 4)

    def testLoopback(self):
        server = http.HTTPChannel()
        server.requestFactory = DummyHTTPHandlerProxy
        client = LoopbackHTTPClient()
        client.handleResponse = self._handleResponse
        client.handleHeader = self._handleHeader
        client.handleEndHeaders = self._handleEndHeaders
        client.handleStatus = self._handleStatus
        d = loopback.loopbackAsync(server, client)
        d.addCallback(self._cbTestLoopback)
        return d

    def _cbTestLoopback(self, ignored):
        if not (self.gotStatus and self.gotResponse and self.gotEndHeaders):
            raise RuntimeError(
                "didn't get all callbacks {}".format(
                    [self.gotStatus, self.gotResponse, self.gotEndHeaders],
                )
            )
        del self.gotEndHeaders
        del self.gotResponse
        del self.gotStatus
        del self.numHeaders


def _prequest(**headers):
    """
    Make a request with the given request headers for the persistence tests.
    """
    request = http.Request(DummyChannel(), False)
    for headerName, v in headers.items():
        request.requestHeaders.setRawHeaders(networkString(headerName), v)
    return request


class PersistenceTests(unittest.TestCase):
    """
    Tests for persistent HTTP connections.
    """

    def setUp(self):
        self.channel = http.HTTPChannel()
        self.request = _prequest()

    def test_http09(self):
        """
        After being used for an I{HTTP/0.9} request, the L{HTTPChannel} is not
        persistent.
        """
        persist = self.channel.checkPersistence(self.request, b"HTTP/0.9")
        self.assertFalse(persist)
        self.assertEqual([], list(self.request.responseHeaders.getAllRawHeaders()))

    def test_http10(self):
        """
        After being used for an I{HTTP/1.0} request, the L{HTTPChannel} is not
        persistent.
        """
        persist = self.channel.checkPersistence(self.request, b"HTTP/1.0")
        self.assertFalse(persist)
        self.assertEqual([], list(self.request.responseHeaders.getAllRawHeaders()))

    def test_http11(self):
        """
        After being used for an I{HTTP/1.1} request, the L{HTTPChannel} is
        persistent.
        """
        persist = self.channel.checkPersistence(self.request, b"HTTP/1.1")
        self.assertTrue(persist)
        self.assertEqual([], list(self.request.responseHeaders.getAllRawHeaders()))

    def test_http11Close(self):
        """
        After being used for an I{HTTP/1.1} request with a I{Connection: Close}
        header, the L{HTTPChannel} is not persistent.
        """
        request = _prequest(connection=[b"close"])
        persist = self.channel.checkPersistence(request, b"HTTP/1.1")
        self.assertFalse(persist)
        self.assertEqual(
            [(b"Connection", [b"close"])],
            list(request.responseHeaders.getAllRawHeaders()),
        )


class IdentityTransferEncodingTests(TestCase):
    """
    Tests for L{_IdentityTransferDecoder}.
    """

    def setUp(self):
        """
        Create an L{_IdentityTransferDecoder} with callbacks hooked up so that
        calls to them can be inspected.
        """
        self.data = []
        self.finish = []
        self.contentLength = 10
        self.decoder = _IdentityTransferDecoder(
            self.contentLength, self.data.append, self.finish.append
        )

    def test_exactAmountReceived(self):
        """
        If L{_IdentityTransferDecoder.dataReceived} is called with a byte string
        with length equal to the content length passed to
        L{_IdentityTransferDecoder}'s initializer, the data callback is invoked
        with that string and the finish callback is invoked with a zero-length
        string.
        """
        self.decoder.dataReceived(b"x" * self.contentLength)
        self.assertEqual(self.data, [b"x" * self.contentLength])
        self.assertEqual(self.finish, [b""])

    def test_shortStrings(self):
        """
        If L{_IdentityTransferDecoder.dataReceived} is called multiple times
        with byte strings which, when concatenated, are as long as the content
        length provided, the data callback is invoked with each string and the
        finish callback is invoked only after the second call.
        """
        self.decoder.dataReceived(b"x")
        self.assertEqual(self.data, [b"x"])
        self.assertEqual(self.finish, [])
        self.decoder.dataReceived(b"y" * (self.contentLength - 1))
        self.assertEqual(self.data, [b"x", b"y" * (self.contentLength - 1)])
        self.assertEqual(self.finish, [b""])

    def test_longString(self):
        """
        If L{_IdentityTransferDecoder.dataReceived} is called with a byte string
        with length greater than the provided content length, only the prefix
        of that string up to the content length is passed to the data callback
        and the remainder is passed to the finish callback.
        """
        self.decoder.dataReceived(b"x" * self.contentLength + b"y")
        self.assertEqual(self.data, [b"x" * self.contentLength])
        self.assertEqual(self.finish, [b"y"])

    def test_rejectDataAfterFinished(self):
        """
        If data is passed to L{_IdentityTransferDecoder.dataReceived} after the
        finish callback has been invoked, C{RuntimeError} is raised.
        """
        failures = []

        def finish(bytes):
            try:
                decoder.dataReceived(b"foo")
            except BaseException:
                failures.append(Failure())

        decoder = _IdentityTransferDecoder(5, self.data.append, finish)
        decoder.dataReceived(b"x" * 4)
        self.assertEqual(failures, [])
        decoder.dataReceived(b"y")
        failures[0].trap(RuntimeError)
        self.assertEqual(
            str(failures[0].value),
            "_IdentityTransferDecoder cannot decode data after finishing",
        )

    def test_unknownContentLength(self):
        """
        If L{_IdentityTransferDecoder} is constructed with L{None} for the
        content length, it passes all data delivered to it through to the data
        callback.
        """
        data = []
        finish = []
        decoder = _IdentityTransferDecoder(None, data.append, finish.append)
        decoder.dataReceived(b"x")
        self.assertEqual(data, [b"x"])
        decoder.dataReceived(b"y")
        self.assertEqual(data, [b"x", b"y"])
        self.assertEqual(finish, [])

    def _verifyCallbacksUnreferenced(self, decoder):
        """
        Check the decoder's data and finish callbacks and make sure they are
        None in order to help avoid references cycles.
        """
        self.assertIdentical(decoder.dataCallback, None)
        self.assertIdentical(decoder.finishCallback, None)

    def test_earlyConnectionLose(self):
        """
        L{_IdentityTransferDecoder.noMoreData} raises L{_DataLoss} if it is
        called and the content length is known but not enough bytes have been
        delivered.
        """
        self.decoder.dataReceived(b"x" * (self.contentLength - 1))
        self.assertRaises(_DataLoss, self.decoder.noMoreData)
        self._verifyCallbacksUnreferenced(self.decoder)

    def test_unknownContentLengthConnectionLose(self):
        """
        L{_IdentityTransferDecoder.noMoreData} calls the finish callback and
        raises L{PotentialDataLoss} if it is called and the content length is
        unknown.
        """
        body = []
        finished = []
        decoder = _IdentityTransferDecoder(None, body.append, finished.append)
        self.assertRaises(PotentialDataLoss, decoder.noMoreData)
        self.assertEqual(body, [])
        self.assertEqual(finished, [b""])
        self._verifyCallbacksUnreferenced(decoder)

    def test_finishedConnectionLose(self):
        """
        L{_IdentityTransferDecoder.noMoreData} does not raise any exception if
        it is called when the content length is known and that many bytes have
        been delivered.
        """
        self.decoder.dataReceived(b"x" * self.contentLength)
        self.decoder.noMoreData()
        self._verifyCallbacksUnreferenced(self.decoder)


class ChunkedTransferEncodingTests(unittest.TestCase):
    """
    Tests for L{_ChunkedTransferDecoder}, which turns a byte stream encoded
    using HTTP I{chunked} C{Transfer-Encoding} back into the original byte
    stream.
    """

    def test_decoding(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} decodes chunked-encoded data
        and passes the result to the specified callback.
        """
        L = []
        p = http._ChunkedTransferDecoder(L.append, None)
        p.dataReceived(b"3\r\nabc\r\n5\r\n12345\r\n")
        p.dataReceived(b"a\r\n0123456789\r\n")
        self.assertEqual(L, [b"abc", b"12345", b"0123456789"])

    def test_short(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} decodes chunks broken up and
        delivered in multiple calls.
        """
        L = []
        finished = []
        p = http._ChunkedTransferDecoder(L.append, finished.append)
        for s in iterbytes(b"3\r\nabc\r\n5\r\n12345\r\n0\r\n\r\n"):
            p.dataReceived(s)
        self.assertEqual(L, [b"a", b"b", b"c", b"1", b"2", b"3", b"4", b"5"])
        self.assertEqual(finished, [b""])

    def test_long(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} delivers partial chunk data as
        soon as it is received.
        """
        data = []
        finished = []
        p = http._ChunkedTransferDecoder(data.append, finished.append)
        p.dataReceived(b"a;\r\n12345")
        p.dataReceived(b"67890")
        p.dataReceived(b"\r\n0;\r\n\r\n...")
        self.assertEqual(data, [b"12345", b"67890"])
        self.assertEqual(finished, [b"..."])

    def test_empty(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} is robust against receiving
        a zero-length input.
        """
        chunks = []
        finished = []
        p = http._ChunkedTransferDecoder(chunks.append, finished.append)
        p.dataReceived(b"")
        for s in iterbytes(b"3\r\nabc\r\n5\r\n12345\r\n0\r\n\r\n"):
            p.dataReceived(s)
            p.dataReceived(b"")
        self.assertEqual(chunks, [b"a", b"b", b"c", b"1", b"2", b"3", b"4", b"5"])
        self.assertEqual(finished, [b""])

    def test_newlines(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} doesn't treat CR LF pairs
        embedded in chunk bodies specially.
        """
        L = []
        p = http._ChunkedTransferDecoder(L.append, None)
        p.dataReceived(b"2\r\n\r\n\r\n")
        self.assertEqual(L, [b"\r\n"])

    def test_extensions(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} disregards chunk-extension
        fields.
        """
        L = []
        p = http._ChunkedTransferDecoder(L.append, None)
        p.dataReceived(b"3; x-foo=bar\r\nabc\r\n")
        self.assertEqual(L, [b"abc"])

    def test_extensionsMalformed(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the chunk extension fields contain
        invalid characters.

        This is a potential request smuggling vector: see GHSA-c2jg-hw38-jrqq.
        """
        invalidControl = (
            b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\n\x0b\x0c\r\x0e\x0f"
            b"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
        )
        invalidDelimiter = b"\\"
        invalidDel = b"\x7f"
        for b in invalidControl + invalidDelimiter + invalidDel:
            data = b"3; " + bytes((b,)) + b"\r\nabc\r\n"
            p = http._ChunkedTransferDecoder(
                lambda b: None,  # pragma: nocov
                lambda b: None,  # pragma: nocov
            )
            self.assertRaises(http._MalformedChunkedDataError, p.dataReceived, data)

    def test_oversizedChunkSizeLine(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the chunk size line exceeds 4 KiB.
        This applies even when the data has already been received and buffered
        so that behavior is consistent regardless of how bytes are framed.
        """
        p = http._ChunkedTransferDecoder(None, None)
        self.assertRaises(
            http._MalformedChunkedDataError,
            p.dataReceived,
            b"3;" + b"." * http.maxChunkSizeLineLength + b"\r\nabc\r\n",
        )

    def test_oversizedChunkSizeLinePartial(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the amount of data buffered while
        looking for the end of the chunk size line exceeds 4 KiB so
        that buffering does not continue without bound.
        """
        p = http._ChunkedTransferDecoder(None, None)
        self.assertRaises(
            http._MalformedChunkedDataError,
            p.dataReceived,
            b"." * (http.maxChunkSizeLineLength + 1),
        )

    def test_malformedChunkSize(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the chunk size can't be decoded as
        a base-16 integer.
        """
        p = http._ChunkedTransferDecoder(
            lambda b: None,  # pragma: nocov
            lambda b: None,  # pragma: nocov
        )
        self.assertRaises(
            http._MalformedChunkedDataError, p.dataReceived, b"bloop\r\nabc\r\n"
        )

    def test_malformedChunkSizeNegative(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the chunk size is negative.
        """
        p = http._ChunkedTransferDecoder(
            lambda b: None,  # pragma: nocov
            lambda b: None,  # pragma: nocov
        )
        self.assertRaises(
            http._MalformedChunkedDataError, p.dataReceived, b"-3\r\nabc\r\n"
        )

    def test_malformedChunkSizeHex(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the chunk size is prefixed with
        "0x", as if it were a Python integer literal.

        This is a potential request smuggling vector: see GHSA-c2jg-hw38-jrqq.
        """
        p = http._ChunkedTransferDecoder(
            lambda b: None,  # pragma: nocov
            lambda b: None,  # pragma: nocov
        )
        self.assertRaises(
            http._MalformedChunkedDataError, p.dataReceived, b"0x3\r\nabc\r\n"
        )

    def test_malformedChunkEnd(self):
        r"""
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the chunk is followed by characters
        other than C{\r\n}.
        """
        p = http._ChunkedTransferDecoder(
            lambda b: None,
            lambda b: None,  # pragma: nocov
        )
        self.assertRaises(
            http._MalformedChunkedDataError, p.dataReceived, b"3\r\nabc!!!!"
        )

    def test_malformedChunkEndFinal(self):
        r"""
        L{_ChunkedTransferDecoder.dataReceived} raises
        L{_MalformedChunkedDataError} when the terminal zero-length chunk is
        followed by characters other than C{\r\n}.
        """
        p = http._ChunkedTransferDecoder(
            lambda b: None,
            lambda b: None,  # pragma: nocov
        )
        self.assertRaises(
            http._MalformedChunkedDataError, p.dataReceived, b"3\r\nabc\r\n0\r\n!!"
        )

    def test_finish(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} interprets a zero-length
        chunk as the end of the chunked data stream and calls the completion
        callback.
        """
        finished = []
        p = http._ChunkedTransferDecoder(None, finished.append)
        p.dataReceived(b"0\r\n\r\n")
        self.assertEqual(finished, [b""])

    def test_extra(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} passes any bytes which come
        after the terminating zero-length chunk to the completion callback.
        """
        finished = []
        p = http._ChunkedTransferDecoder(None, finished.append)
        p.dataReceived(b"0\r\n\r\nhello")
        self.assertEqual(finished, [b"hello"])

    def test_afterFinished(self):
        """
        L{_ChunkedTransferDecoder.dataReceived} raises C{RuntimeError} if it
        is called after it has seen the last chunk.
        """
        p = http._ChunkedTransferDecoder(None, lambda bytes: None)
        p.dataReceived(b"0\r\n\r\n")
        self.assertRaises(RuntimeError, p.dataReceived, b"hello")

    def test_earlyConnectionLose(self):
        """
        L{_ChunkedTransferDecoder.noMoreData} raises L{_DataLoss} if it is
        called and the end of the last trailer has not yet been received.
        """
        parser = http._ChunkedTransferDecoder(None, lambda bytes: None)
        parser.dataReceived(b"0\r\n\r")
        exc = self.assertRaises(_DataLoss, parser.noMoreData)
        self.assertEqual(
            str(exc),
            "Chunked decoder in 'TRAILER' state, still expecting more data "
            "to get to 'FINISHED' state.",
        )

    def test_finishedConnectionLose(self):
        """
        L{_ChunkedTransferDecoder.noMoreData} does not raise any exception if
        it is called after the terminal zero length chunk is received.
        """
        parser = http._ChunkedTransferDecoder(None, lambda bytes: None)
        parser.dataReceived(b"0\r\n\r\n")
        parser.noMoreData()

    def test_reentrantFinishedNoMoreData(self):
        """
        L{_ChunkedTransferDecoder.noMoreData} can be called from the finished
        callback without raising an exception.
        """
        errors = []
        successes = []

        def finished(extra):
            try:
                parser.noMoreData()
            except BaseException:
                errors.append(Failure())
            else:
                successes.append(True)

        parser = http._ChunkedTransferDecoder(None, finished)
        parser.dataReceived(b"0\r\n\r\n")
        self.assertEqual(errors, [])
        self.assertEqual(successes, [True])


class ChunkingTests(unittest.TestCase, ResponseTestMixin):

    strings = [b"abcv", b"", b"fdfsd423", b"Ffasfas\r\n", b"523523\n\rfsdf", b"4234"]

    def testChunks(self):
        for s in self.strings:
            chunked = b"".join(http.toChunk(s))
            self.assertEqual((s, b""), http.fromChunk(chunked))
        self.assertRaises(ValueError, http.fromChunk, b"-5\r\nmalformed!\r\n")
        self.assertRaises(ValueError, http.fromChunk, b"0xa\r\nmalformed!\r\n")
        self.assertRaises(ValueError, http.fromChunk, b"0XA\r\nmalformed!\r\n")

    def testConcatenatedChunks(self):
        chunked = b"".join([b"".join(http.toChunk(t)) for t in self.strings])
        result = []
        buffer = b""
        for c in iterbytes(chunked):
            buffer = buffer + c
            try:
                data, buffer = http.fromChunk(buffer)
                result.append(data)
            except ValueError:
                pass
        self.assertEqual(result, self.strings)

    def test_chunkedResponses(self):
        """
        Test that the L{HTTPChannel} correctly chunks responses when needed.
        """
        trans = StringTransport()
        channel = http.HTTPChannel()
        channel.makeConnection(trans)

        req = http.Request(channel, False)

        req.setResponseCode(200)
        req.clientproto = b"HTTP/1.1"
        req.responseHeaders.setRawHeaders(b"test", [b"lemur"])
        req.write(b"Hello")
        req.write(b"World!")

        self.assertResponseEquals(
            trans.value(),
            [
                (
                    b"HTTP/1.1 200 OK",
                    b"Test: lemur",
                    b"Transfer-Encoding: chunked",
                    b"5\r\nHello\r\n6\r\nWorld!\r\n",
                )
            ],
        )

    def runChunkedRequest(self, httpRequest, requestFactory=None, chunkSize=1):
        """
        Execute a web request based on plain text content, chunking
        the request payload.

        This is a stripped-down, chunking version of ParsingTests.runRequest.
        """
        channel = http.HTTPChannel()

        if requestFactory:
            channel.requestFactory = _makeRequestProxyFactory(requestFactory)

        httpRequest = httpRequest.replace(b"\n", b"\r\n")
        header, body = httpRequest.split(b"\r\n\r\n", 1)

        transport = StringTransport()

        channel.makeConnection(transport)
        channel.dataReceived(header + b"\r\n\r\n")

        for pos in range(len(body) // chunkSize + 1):
            if channel.transport.disconnecting:
                break
            channel.dataReceived(
                b"".join(http.toChunk(body[pos * chunkSize : (pos + 1) * chunkSize]))
            )

        channel.dataReceived(b"".join(http.toChunk(b"")))
        channel.connectionLost(IOError("all done"))

        return channel

    def test_multipartFormData(self):
        """
        Test that chunked uploads are actually processed into args.

        This is essentially a copy of ParsingTests.test_multipartFormData,
        just with chunking put in.

        This fails as of twisted version 18.9.0 because of bug #9678.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.write(b"done")
                self.finish()

        req = b"""\
POST / HTTP/1.0
Content-Type: multipart/form-data; boundary=AaB03x
Transfer-Encoding: chunked

--AaB03x
Content-Type: text/plain
Content-Disposition: form-data; name="text"
Content-Transfer-Encoding: quoted-printable

abasdfg
--AaB03x--
"""
        channel = self.runChunkedRequest(req, MyRequest, chunkSize=5)
        self.assertEqual(channel.transport.value(), b"HTTP/1.0 200 OK\r\n\r\ndone")
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0].args, {b"text": [b"abasdfg"]})


class ParsingTests(unittest.TestCase):
    """
    Tests for protocol parsing in L{HTTPChannel}.
    """

    def setUp(self):
        self.didRequest = False

    def runRequest(self, httpRequest, requestFactory=None, success=True, channel=None):
        """
        Execute a web request based on plain text content.

        @param httpRequest: Content for the request which is processed. Each
            L{"\n"} will be replaced with L{"\r\n"}.
        @type httpRequest: C{bytes}

        @param requestFactory: 2-argument callable returning a Request.
        @type requestFactory: C{callable}

        @param success: Value to compare against I{self.didRequest}.
        @type success: C{bool}

        @param channel: Channel instance over which the request is processed.
        @type channel: L{HTTPChannel}

        @return: Returns the channel used for processing the request.
        @rtype: L{HTTPChannel}
        """
        if not channel:
            channel = http.HTTPChannel()

        if requestFactory:
            channel.requestFactory = _makeRequestProxyFactory(requestFactory)

        httpRequest = httpRequest.replace(b"\n", b"\r\n")
        transport = StringTransport()

        channel.makeConnection(transport)
        # one byte at a time, to stress it.
        for byte in iterbytes(httpRequest):
            if channel.transport.disconnecting:
                break
            channel.dataReceived(byte)
        channel.connectionLost(IOError("all done"))

        if success:
            self.assertTrue(self.didRequest)
        else:
            self.assertFalse(self.didRequest)
        return channel

    def assertRequestRejected(self, requestLines):
        """
        Execute a HTTP request and assert that it is rejected with a 400 Bad
        Response and disconnection.

        @param requestLines: Plain text lines of the request. These lines will
            be joined with newlines to form the HTTP request that is processed.
        @type requestLines: C{list} of C{bytes}
        """
        httpRequest = b"\n".join(requestLines)
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        channel = self.runRequest(httpRequest, MyRequest, success=False)
        self.assertEqual(
            channel.transport.value(),
            b"HTTP/1.1 400 Bad Request\r\n\r\n",
        )
        self.assertTrue(channel.transport.disconnecting)
        self.assertEqual(processed, [])

    def test_invalidNonAsciiMethod(self):
        """
        When client sends invalid HTTP method containing
        non-ascii characters HTTP 400 'Bad Request' status will be returned.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        badRequestLine = b"GE\xc2\xa9 / HTTP/1.1\r\n\r\n"
        channel = self.runRequest(badRequestLine, MyRequest, 0)
        self.assertEqual(channel.transport.value(), b"HTTP/1.1 400 Bad Request\r\n\r\n")
        self.assertTrue(channel.transport.disconnecting)
        self.assertEqual(processed, [])

    def test_basicAuth(self):
        """
        L{HTTPChannel} provides username and password information supplied in
        an I{Authorization} header to the L{Request} which makes it available
        via its C{getUser} and C{getPassword} methods.
        """
        requests = []

        class Request(http.Request):
            def process(self):
                self.credentials = (self.getUser(), self.getPassword())
                requests.append(self)

        for u, p in [(b"foo", b"bar"), (b"hello", b"there:z")]:
            s = base64.b64encode(b":".join((u, p)))
            f = b"GET / HTTP/1.0\nAuthorization: Basic " + s + b"\n\n"
            self.runRequest(f, Request, 0)
            req = requests.pop()
            self.assertEqual((u, p), req.credentials)

    def test_headers(self):
        """
        Headers received by L{HTTPChannel} in a request are made available to
        the L{Request}.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        requestLines = [
            b"GET / HTTP/1.0",
            b"Foo: bar",
            b"baz: Quux",
            b"baz: quux",
            b"",
            b"",
        ]

        self.runRequest(b"\n".join(requestLines), MyRequest, 0)
        [request] = processed
        self.assertEqual(request.requestHeaders.getRawHeaders(b"foo"), [b"bar"])
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"bAz"), [b"Quux", b"quux"]
        )

    def test_headersMultiline(self):
        """
        Line folded headers are handled by L{HTTPChannel} by replacing each
        fold with a single space by the time they are made available to the
        L{Request}. Any leading whitespace in the folded lines of the header
        value is replaced with a single space, per:

            A server that receives an obs-fold in a request message ... MUST
            ... replace each received obs-fold with one or more SP octets prior
            to interpreting the field value or forwarding the message
            downstream.

        See RFC 7230 section 3.2.4.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        requestLines = [
            b"GET / HTTP/1.0",
            b"nospace: ",
            b" nospace\t",
            b"space:space",
            b" space",
            b"spaces: spaces",
            b"  spaces",
            b"   spaces",
            b"tab: t",
            b"\ta",
            b"\tb",
            b"",
            b"",
        ]

        self.runRequest(b"\n".join(requestLines), MyRequest, 0)
        [request] = processed
        # All leading and trailing whitespace is stripped from the
        # header-value.
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"nospace"),
            [b"nospace"],
        )
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"space"),
            [b"space space"],
        )
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"spaces"),
            [b"spaces spaces spaces"],
        )
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"tab"),
            [b"t a b"],
        )

    def test_headerStripWhitespace(self):
        """
        Leading and trailing space and tab characters are stripped from
        headers. Other forms of whitespace are preserved.

        See RFC 7230 section 3.2.3 and 3.2.4.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        requestLines = [
            b"GET / HTTP/1.0",
            b"spaces:   spaces were stripped   ",
            b"tabs: \t\ttabs were stripped\t\t",
            b"spaces-and-tabs: \t \t spaces and tabs were stripped\t \t",
            b"line-tab:   \v vertical tab was preserved\v\t",
            b"form-feed: \f form feed was preserved \f  ",
            b"",
            b"",
        ]

        self.runRequest(b"\n".join(requestLines), MyRequest, 0)
        [request] = processed
        # All leading and trailing whitespace is stripped from the
        # header-value.
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"spaces"),
            [b"spaces were stripped"],
        )
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"tabs"),
            [b"tabs were stripped"],
        )
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"spaces-and-tabs"),
            [b"spaces and tabs were stripped"],
        )
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"line-tab"),
            [b"\v vertical tab was preserved\v"],
        )
        self.assertEqual(
            request.requestHeaders.getRawHeaders(b"form-feed"),
            [b"\f form feed was preserved \f"],
        )

    def test_tooManyHeaders(self):
        """
        C{HTTPChannel} enforces a limit of C{HTTPChannel.maxHeaders} on the
        number of headers received per request.
        """
        requestLines = [b"GET / HTTP/1.0"]
        for i in range(http.HTTPChannel.maxHeaders + 2):
            requestLines.append(networkString(f"{i}: foo"))
        requestLines.extend([b"", b""])

        self.assertRequestRejected(requestLines)

    def test_invalidContentLengthHeader(self):
        """
        If a I{Content-Length} header with a non-integer value is received,
        a 400 (Bad Request) response is sent to the client and the connection
        is closed.
        """
        self.assertRequestRejected(
            [
                b"GET / HTTP/1.0",
                b"Content-Length: x",
                b"",
                b"",
            ]
        )

    def test_invalidHeaderNoColon(self):
        """
        If a header without colon is received a 400 (Bad Request) response
        is sent to the client and the connection is closed.
        """
        self.assertRequestRejected(
            [
                b"GET / HTTP/1.0",
                b"HeaderName ",
                b"",
                b"",
            ]
        )

    def test_invalidHeaderOnlyColon(self):
        """
        C{HTTPChannel} rejects a request with an empty header name (i.e.
        nothing before the colon).  It produces a 400 (Bad Request) response is
        generated and closes the connection.
        """
        self.assertRequestRejected(
            [
                b"GET / HTTP/1.0",
                b": foo",
                b"",
                b"",
            ]
        )

    def test_invalidHeaderWhitespaceBeforeColon(self):
        """
        C{HTTPChannel} rejects a request containing a header with whitespace
        between the header name and colon as requried by RFC 7230 section
        3.2.4. A 400 (Bad Request) response is generated and the connection
        closed.
        """
        self.assertRequestRejected(
            [
                b"GET / HTTP/1.0",
                b"HeaderName : foo",
                b"",
                b"",
            ]
        )

    def test_headerLimitPerRequest(self):
        """
        C{HTTPChannel} enforces the limit of C{HTTPChannel.maxHeaders} per
        request so that headers received in an earlier request do not count
        towards the limit when processing a later request.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        self.patch(http.HTTPChannel, "maxHeaders", 1)
        requestLines = [
            b"GET / HTTP/1.1",
            b"Foo: bar",
            b"",
            b"",
            b"GET / HTTP/1.1",
            b"Bar: baz",
            b"",
            b"",
        ]

        channel = self.runRequest(b"\n".join(requestLines), MyRequest, 0)
        [first, second] = processed
        self.assertEqual(first.getHeader(b"foo"), b"bar")
        self.assertEqual(second.getHeader(b"bar"), b"baz")
        self.assertEqual(
            channel.transport.value(),
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"0\r\n"
            b"\r\n"
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"0\r\n"
            b"\r\n",
        )

    def test_headersTooBigInitialCommand(self):
        """
        Enforces a limit of C{HTTPChannel.totalHeadersSize}
        on the size of headers received per request starting from initial
        command line.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        channel = http.HTTPChannel()
        channel.totalHeadersSize = 10
        httpRequest = b"GET /path/longer/than/10 HTTP/1.1\n"

        channel = self.runRequest(
            httpRequest=httpRequest,
            requestFactory=MyRequest,
            channel=channel,
            success=False,
        )

        self.assertEqual(processed, [])
        self.assertEqual(channel.transport.value(), b"HTTP/1.1 400 Bad Request\r\n\r\n")

    def test_headersTooBigOtherHeaders(self):
        """
        Enforces a limit of C{HTTPChannel.totalHeadersSize}
        on the size of headers received per request counting first line
        and total headers.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.finish()

        channel = http.HTTPChannel()
        channel.totalHeadersSize = 40
        httpRequest = b"GET /less/than/40 HTTP/1.1\n" b"Some-Header: less-than-40\n"

        channel = self.runRequest(
            httpRequest=httpRequest,
            requestFactory=MyRequest,
            channel=channel,
            success=False,
        )

        self.assertEqual(processed, [])
        self.assertEqual(channel.transport.value(), b"HTTP/1.1 400 Bad Request\r\n\r\n")

    def test_headersTooBigPerRequest(self):
        """
        Enforces total size of headers per individual request and counter
        is reset at the end of each request.
        """

        class SimpleRequest(http.Request):
            def process(self):
                self.finish()

        channel = http.HTTPChannel()
        channel.totalHeadersSize = 60
        channel.requestFactory = SimpleRequest
        httpRequest = (
            b"GET / HTTP/1.1\n"
            b"Some-Header: total-less-than-60\n"
            b"\n"
            b"GET / HTTP/1.1\n"
            b"Some-Header: less-than-60\n"
            b"\n"
        )

        channel = self.runRequest(
            httpRequest=httpRequest, channel=channel, success=False
        )

        self.assertEqual(
            channel.transport.value(),
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"0\r\n"
            b"\r\n"
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"0\r\n"
            b"\r\n",
        )

    def testCookies(self):
        """
        Test cookies parsing and reading.
        """
        httpRequest = b"""\
GET / HTTP/1.0
Cookie: rabbit="eat carrot"; ninja=secret; spam="hey 1=1!"

"""
        cookies = {}
        testcase = self

        class MyRequest(http.Request):
            def process(self):
                for name in [b"rabbit", b"ninja", b"spam"]:
                    cookies[name] = self.getCookie(name)
                testcase.didRequest = True
                self.finish()

        self.runRequest(httpRequest, MyRequest)

        self.assertEqual(
            cookies,
            {b"rabbit": b'"eat carrot"', b"ninja": b"secret", b"spam": b'"hey 1=1!"'},
        )

    def testGET(self):
        httpRequest = b"""\
GET /?key=value&multiple=two+words&multiple=more%20words&empty= HTTP/1.0

"""
        method = []
        args = []
        testcase = self

        class MyRequest(http.Request):
            def process(self):
                method.append(self.method)
                args.extend(
                    [self.args[b"key"], self.args[b"empty"], self.args[b"multiple"]]
                )
                testcase.didRequest = True
                self.finish()

        self.runRequest(httpRequest, MyRequest)
        self.assertEqual(method, [b"GET"])
        self.assertEqual(args, [[b"value"], [b""], [b"two words", b"more words"]])

    def test_extraQuestionMark(self):
        """
        While only a single '?' is allowed in an URL, several other servers
        allow several and pass all after the first through as part of the
        query arguments.  Test that we emulate this behavior.
        """
        httpRequest = b"GET /foo?bar=?&baz=quux HTTP/1.0\n\n"

        method = []
        path = []
        args = []
        testcase = self

        class MyRequest(http.Request):
            def process(self):
                method.append(self.method)
                path.append(self.path)
                args.extend([self.args[b"bar"], self.args[b"baz"]])
                testcase.didRequest = True
                self.finish()

        self.runRequest(httpRequest, MyRequest)
        self.assertEqual(method, [b"GET"])
        self.assertEqual(path, [b"/foo"])
        self.assertEqual(args, [[b"?"], [b"quux"]])

    def test_formPOSTRequest(self):
        """
        The request body of a I{POST} request with a I{Content-Type} header
        of I{application/x-www-form-urlencoded} is parsed according to that
        content type and made available in the C{args} attribute of the
        request object.  The original bytes of the request may still be read
        from the C{content} attribute.
        """
        query = "key=value&multiple=two+words&multiple=more%20words&empty="
        httpRequest = networkString(
            """\
POST / HTTP/1.0
Content-Length: %d
Content-Type: application/x-www-form-urlencoded

%s"""
            % (len(query), query)
        )

        method = []
        args = []
        content = []
        testcase = self

        class MyRequest(http.Request):
            def process(self):
                method.append(self.method)
                args.extend(
                    [self.args[b"key"], self.args[b"empty"], self.args[b"multiple"]]
                )
                content.append(self.content.read())
                testcase.didRequest = True
                self.finish()

        self.runRequest(httpRequest, MyRequest)
        self.assertEqual(method, [b"POST"])
        self.assertEqual(args, [[b"value"], [b""], [b"two words", b"more words"]])
        # Reading from the content file-like must produce the entire request
        # body.
        self.assertEqual(content, [networkString(query)])

    def test_multipartProcessingFailure(self):
        """
        When the multipart processing fails the client gets a 400 Bad Request.
        """
        # The parsing failure is having a UTF-8 boundary -- the spec
        # says it must be ASCII.
        req = b"""\
POST / HTTP/1.0
Content-Type: multipart/form-data; boundary=\xe2\x98\x83
Content-Length: 103

--\xe2\x98\x83
Content-Type: text/plain
Content-Length: 999999999999999999999999999999999999999999999999999999999999999
Content-Transfer-Encoding: quoted-printable

abasdfg
--\xe2\x98\x83--
"""
        channel = self.runRequest(req, http.Request, success=False)
        self.assertEqual(channel.transport.value(), b"HTTP/1.1 400 Bad Request\r\n\r\n")

    def test_multipartEmptyHeaderProcessingFailure(self):
        """
        When the multipart does not contain a header is should be skipped
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.write(b"done")
                self.finish()

        # The parsing failure is encoding a NoneType key when name is not
        # defined in Content-Disposition
        req = b"""\
POST / HTTP/1.0
Content-Type: multipart/form-data; boundary=AaBb1313
Content-Length: 14

--AaBb1313

--AaBb1313--
"""
        channel = self.runRequest(req, MyRequest, success=False)
        self.assertEqual(channel.transport.value(), b"HTTP/1.0 200 OK\r\n\r\ndone")
        self.assertEqual(processed[0].args, {})

    def test_multipartFormData(self):
        """
        If the request has a Content-Type of C{multipart/form-data}, and the
        form data is parseable, the form arguments will be added to the
        request's args.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.write(b"done")
                self.finish()

        req = b"""\
POST / HTTP/1.0
Content-Type: multipart/form-data; boundary=AaB03x
Content-Length: 149

--AaB03x
Content-Type: text/plain
Content-Disposition: form-data; name="text"
Content-Transfer-Encoding: quoted-printable

abasdfg
--AaB03x--
"""
        channel = self.runRequest(req, MyRequest, success=False)
        self.assertEqual(channel.transport.value(), b"HTTP/1.0 200 OK\r\n\r\ndone")
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0].args, {b"text": [b"abasdfg"]})

    def test_multipartFileData(self):
        """
        If the request has a Content-Type of C{multipart/form-data},
        and the form data is parseable and contains files, the file
        portions will be added to the request's args.
        """
        processed = []

        class MyRequest(http.Request):
            def process(self):
                processed.append(self)
                self.write(b"done")
                self.finish()

        body = b"""-----------------------------738837029596785559389649595
Content-Disposition: form-data; name="uploadedfile"; filename="test"
Content-Type: application/octet-stream

abasdfg
-----------------------------738837029596785559389649595--
"""

        req = (
            """\
POST / HTTP/1.0
Content-Type: multipart/form-data; boundary=---------------------------738837029596785559389649595
Content-Length: """
            + str(len(body.replace(b"\n", b"\r\n")))
            + """


"""
        )
        channel = self.runRequest(req.encode("ascii") + body, MyRequest, success=False)
        self.assertEqual(channel.transport.value(), b"HTTP/1.0 200 OK\r\n\r\ndone")
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0].args, {b"uploadedfile": [b"abasdfg"]})

    def test_chunkedEncoding(self):
        """
        If a request uses the I{chunked} transfer encoding, the request body is
        decoded accordingly before it is made available on the request.
        """
        httpRequest = b"""\
GET / HTTP/1.0
Content-Type: text/plain
Transfer-Encoding: chunked

6
Hello,
14
 spam,eggs spam spam
0

"""
        path = []
        method = []
        content = []
        decoder = []
        testcase = self

        class MyRequest(http.Request):
            def process(self):
                content.append(self.content)
                content.append(self.content.read())
                # Don't let it close the original content object.  We want to
                # inspect it later.
                self.content = BytesIO()
                method.append(self.method)
                path.append(self.path)
                decoder.append(self.channel._transferDecoder)
                testcase.didRequest = True
                self.finish()

        self.runRequest(httpRequest, MyRequest)

        # We took responsibility for closing this when we replaced the request
        # attribute, above.
        self.addCleanup(content[0].close)

        assertIsFilesystemTemporary(self, content[0])
        self.assertEqual(content[1], b"Hello, spam,eggs spam spam")
        self.assertEqual(method, [b"GET"])
        self.assertEqual(path, [b"/"])
        self.assertEqual(decoder, [None])

    def test_malformedChunkedEncoding(self):
        """
        If a request uses the I{chunked} transfer encoding, but provides an
        invalid chunk length value, the request fails with a 400 error.
        """
        # See test_chunkedEncoding for the correct form of this request.
        httpRequest = b"""\
GET / HTTP/1.1
Content-Type: text/plain
Transfer-Encoding: chunked

MALFORMED_LINE_THIS_SHOULD_BE_'6'
Hello,
14
 spam,eggs spam spam
0

"""
        didRequest = []

        class MyRequest(http.Request):
            def process(self):
                # This request should fail, so this should never be called.
                didRequest.append(True)

        channel = self.runRequest(httpRequest, MyRequest, success=False)
        self.assertFalse(didRequest, "Request.process called")
        self.assertEqual(channel.transport.value(), b"HTTP/1.1 400 Bad Request\r\n\r\n")
        self.assertTrue(channel.transport.disconnecting)

    def test_basicAuthException(self):
        """
        A L{Request} that throws an exception processing basic authorization
        logs an error and uses an empty username and password.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)
        requests = []

        class Request(http.Request):
            def process(self):
                self.credentials = (self.getUser(), self.getPassword())
                requests.append(self)

        u = b"foo"
        p = b"bar"
        s = base64.b64encode(b":".join((u, p)))
        f = b"GET / HTTP/1.0\nAuthorization: Basic " + s + b"\n\n"
        self.patch(base64, "b64decode", lambda x: [])
        self.runRequest(f, Request, 0)
        req = requests.pop()
        self.assertEqual((b"", b""), req.credentials)
        self.assertEquals(1, len(logObserver))
        event = logObserver[0]
        f = event["log_failure"]
        self.assertIsInstance(f.value, AttributeError)
        self.flushLoggedErrors(AttributeError)

    def test_duplicateContentLengths(self):
        """
        A request which includes multiple C{content-length} headers
        fails with a 400 response without calling L{Request.process}.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Content-Length: 56",
                b"Content-Length: 0",
                b"Host: host.invalid",
                b"",
                b"",
            ]
        )

    def test_contentLengthMalformed(self):
        """
        A request with a non-integer C{Content-Length} header fails with a 400
        response without calling L{Request.process}.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Content-Length: MORE THAN NINE THOUSAND!",
                b"Host: host.invalid",
                b"",
                b"",
                b"x" * 9001,
            ]
        )

    def test_contentLengthTooPositive(self):
        """
        A request with a C{Content-Length} header that begins with a L{+} fails
        with a 400 response without calling L{Request.process}.

        This is a potential request smuggling vector: see GHSA-c2jg-hw38-jrqq.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Content-Length: +100",
                b"Host: host.invalid",
                b"",
                b"",
                b"x" * 100,
            ]
        )

    def test_contentLengthNegative(self):
        """
        A request with a C{Content-Length} header that is negative fails with
        a 400 response without calling L{Request.process}.

        This is a potential request smuggling vector: see GHSA-c2jg-hw38-jrqq.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Content-Length: -100",
                b"Host: host.invalid",
                b"",
                b"",
                b"x" * 200,
            ]
        )

    def test_duplicateContentLengthsWithPipelinedRequests(self):
        """
        Two pipelined requests, the first of which includes multiple
        C{content-length} headers, trigger a 400 response without
        calling L{Request.process}.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Content-Length: 56",
                b"Content-Length: 0",
                b"Host: host.invalid",
                b"",
                b"",
                b"GET /a HTTP/1.1",
                b"Host: host.invalid",
                b"",
                b"",
            ]
        )

    def test_contentLengthAndTransferEncoding(self):
        """
        A request that includes both C{content-length} and
        C{transfer-encoding} headers fails with a 400 response without
        calling L{Request.process}.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Transfer-Encoding: chunked",
                b"Content-Length: 0",
                b"Host: host.invalid",
                b"",
                b"",
            ]
        )

    def test_contentLengthAndTransferEncodingWithPipelinedRequests(self):
        """
        Two pipelined requests, the first of which includes both
        C{content-length} and C{transfer-encoding} headers, triggers a
        400 response without calling L{Request.process}.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Transfer-Encoding: chunked",
                b"Content-Length: 0",
                b"Host: host.invalid",
                b"",
                b"",
                b"GET /a HTTP/1.1",
                b"Host: host.invalid",
                b"",
                b"",
            ]
        )

    def test_unknownTransferEncoding(self):
        """
        A request whose C{transfer-encoding} header includes a value
        other than C{chunked} or C{identity} fails with a 400 response
        without calling L{Request.process}.
        """
        self.assertRequestRejected(
            [
                b"GET /a HTTP/1.1",
                b"Transfer-Encoding: unknown",
                b"Host: host.invalid",
                b"",
                b"",
            ]
        )

    def test_transferEncodingIdentity(self):
        """
        A request with a valid C{content-length} and a
        C{transfer-encoding} whose value is C{identity} succeeds.
        """
        body = []

        class SuccessfulRequest(http.Request):
            processed = False

            def process(self):
                body.append(self.content.read())
                self.setHeader(b"content-length", b"0")
                self.finish()

        request = b"""\
GET / HTTP/1.1
Host: host.invalid
Content-Length: 2
Transfer-Encoding: identity

ok
"""
        channel = self.runRequest(request, SuccessfulRequest, False)
        self.assertEqual(body, [b"ok"])
        self.assertEqual(
            channel.transport.value(),
            b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",
        )


class QueryArgumentsTests(unittest.TestCase):
    def test_urlparse(self):
        """
        For a given URL, L{http.urlparse} should behave the same as L{urlparse},
        except it should always return C{bytes}, never text.
        """

        def urls():
            for scheme in (b"http", b"https"):
                for host in (b"example.com",):
                    for port in (None, 100):
                        for path in (b"", b"path"):
                            if port is not None:
                                host = host + b":" + networkString(str(port))
                                yield urlunsplit((scheme, host, path, b"", b""))

        def assertSameParsing(url, decode):
            """
            Verify that C{url} is parsed into the same objects by both
            L{http.urlparse} and L{urlparse}.
            """
            urlToStandardImplementation = url
            if decode:
                urlToStandardImplementation = url.decode("ascii")

            # stdlib urlparse will give back whatever type we give it.
            # To be able to compare the values meaningfully, if it gives back
            # unicode, convert all the values to bytes.
            standardResult = urlparse(urlToStandardImplementation)
            if isinstance(standardResult.scheme, str):
                # The choice of encoding is basically irrelevant.  The values
                # are all in ASCII.  UTF-8 is, of course, the correct choice.
                expected = (
                    standardResult.scheme.encode("utf-8"),
                    standardResult.netloc.encode("utf-8"),
                    standardResult.path.encode("utf-8"),
                    standardResult.params.encode("utf-8"),
                    standardResult.query.encode("utf-8"),
                    standardResult.fragment.encode("utf-8"),
                )
            else:
                expected = (
                    standardResult.scheme,
                    standardResult.netloc,
                    standardResult.path,
                    standardResult.params,
                    standardResult.query,
                    standardResult.fragment,
                )

            scheme, netloc, path, params, query, fragment = http.urlparse(url)
            self.assertEqual((scheme, netloc, path, params, query, fragment), expected)
            self.assertIsInstance(scheme, bytes)
            self.assertIsInstance(netloc, bytes)
            self.assertIsInstance(path, bytes)
            self.assertIsInstance(params, bytes)
            self.assertIsInstance(query, bytes)
            self.assertIsInstance(fragment, bytes)

        # With caching, unicode then str
        clear_cache()
        for url in urls():
            assertSameParsing(url, True)
            assertSameParsing(url, False)

        # With caching, str then unicode
        clear_cache()
        for url in urls():
            assertSameParsing(url, False)
            assertSameParsing(url, True)

        # Without caching
        for url in urls():
            clear_cache()
            assertSameParsing(url, True)
            clear_cache()
            assertSameParsing(url, False)

    def test_urlparseRejectsUnicode(self):
        """
        L{http.urlparse} should reject unicode input early.
        """
        self.assertRaises(TypeError, http.urlparse, "http://example.org/path")


class ClientDriver(http.HTTPClient):
    def handleStatus(self, version, status, message):
        self.version = version
        self.status = status
        self.message = message


class ClientStatusParsingTests(unittest.TestCase):
    def testBaseline(self):
        c = ClientDriver()
        c.lineReceived(b"HTTP/1.0 201 foo")
        self.assertEqual(c.version, b"HTTP/1.0")
        self.assertEqual(c.status, b"201")
        self.assertEqual(c.message, b"foo")

    def testNoMessage(self):
        c = ClientDriver()
        c.lineReceived(b"HTTP/1.0 201")
        self.assertEqual(c.version, b"HTTP/1.0")
        self.assertEqual(c.status, b"201")
        self.assertEqual(c.message, b"")

    def testNoMessage_trailingSpace(self):
        c = ClientDriver()
        c.lineReceived(b"HTTP/1.0 201 ")
        self.assertEqual(c.version, b"HTTP/1.0")
        self.assertEqual(c.status, b"201")
        self.assertEqual(c.message, b"")


class RequestTests(unittest.TestCase, ResponseTestMixin):
    """
    Tests for L{http.Request}
    """

    def _compatHeadersTest(self, oldName, newName):
        """
        Verify that each of two different attributes which are associated with
        the same state properly reflect changes made through the other.

        This is used to test that the C{headers}/C{responseHeaders} and
        C{received_headers}/C{requestHeaders} pairs interact properly.
        """
        req = http.Request(DummyChannel(), False)
        getattr(req, newName).setRawHeaders(b"test", [b"lemur"])
        self.assertEqual(getattr(req, oldName)[b"test"], b"lemur")
        setattr(req, oldName, {b"foo": b"bar"})
        self.assertEqual(
            list(getattr(req, newName).getAllRawHeaders()), [(b"Foo", [b"bar"])]
        )
        setattr(req, newName, http_headers.Headers())
        self.assertEqual(getattr(req, oldName), {})

    def test_getHeader(self):
        """
        L{http.Request.getHeader} returns the value of the named request
        header.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"test", [b"lemur"])
        self.assertEqual(req.getHeader(b"test"), b"lemur")

    def test_getRequestHostname(self):
        """
        L{http.Request.getRequestHostname} returns the hostname portion of the
        request, based on the C{Host:} header.
        """
        req = http.Request(DummyChannel(), False)

        def check(header, expectedHost):
            req.requestHeaders.setRawHeaders(b"host", [header])
            self.assertEqual(req.getRequestHostname(), expectedHost)

        check(b"example.com", b"example.com")
        check(b"example.com:8443", b"example.com")
        check(b"192.168.1.1", b"192.168.1.1")
        check(b"192.168.1.1:19289", b"192.168.1.1")
        check(b"[2607:f0d0:1002:51::4]", b"2607:f0d0:1002:51::4")
        check(
            b"[2607:f0d0:1002:0051:0000:0000:0000:0004]",
            b"2607:f0d0:1002:0051:0000:0000:0000:0004",
        )
        check(b"[::1]", b"::1")
        check(b"[::1]:8080", b"::1")
        check(b"[2607:f0d0:1002:51::4]:9443", b"2607:f0d0:1002:51::4")

    def test_getHeaderReceivedMultiples(self):
        """
        When there are multiple values for a single request header,
        L{http.Request.getHeader} returns the last value.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"test", [b"lemur", b"panda"])
        self.assertEqual(req.getHeader(b"test"), b"panda")

    def test_getHeaderNotFound(self):
        """
        L{http.Request.getHeader} returns L{None} when asked for the value of a
        request header which is not present.
        """
        req = http.Request(DummyChannel(), False)
        self.assertEqual(req.getHeader(b"test"), None)

    def test_getAllHeaders(self):
        """
        L{http.Request.getAllheaders} returns a C{dict} mapping all request
        header names to their corresponding values.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"test", [b"lemur"])
        self.assertEqual(req.getAllHeaders(), {b"test": b"lemur"})

    def test_getAllHeadersNoHeaders(self):
        """
        L{http.Request.getAllHeaders} returns an empty C{dict} if there are no
        request headers.
        """
        req = http.Request(DummyChannel(), False)
        self.assertEqual(req.getAllHeaders(), {})

    def test_getAllHeadersMultipleHeaders(self):
        """
        When there are multiple values for a single request header,
        L{http.Request.getAllHeaders} returns only the last value.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"test", [b"lemur", b"panda"])
        self.assertEqual(req.getAllHeaders(), {b"test": b"panda"})

    def test_setResponseCode(self):
        """
        L{http.Request.setResponseCode} takes a status code and causes it to be
        used as the response status.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        req.setResponseCode(201)
        req.write(b"")
        self.assertEqual(
            channel.transport.written.getvalue().splitlines()[0],
            b"(no clientproto yet) 201 Created",
        )

    def test_setResponseCodeAndMessage(self):
        """
        L{http.Request.setResponseCode} takes a status code and a message and
        causes them to be used as the response status.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        req.setResponseCode(202, b"happily accepted")
        req.write(b"")
        self.assertEqual(
            channel.transport.written.getvalue().splitlines()[0],
            b"(no clientproto yet) 202 happily accepted",
        )

    def test_setResponseCodeAndMessageNotBytes(self):
        """
        L{http.Request.setResponseCode} accepts C{bytes} for the message
        parameter and raises L{TypeError} if passed anything else.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        self.assertRaises(TypeError, req.setResponseCode, 202, "not happily accepted")

    def test_setResponseCodeAcceptsIntegers(self):
        """
        L{http.Request.setResponseCode} accepts C{int} for the code parameter
        and raises L{TypeError} if passed anything else.
        """
        req = http.Request(DummyChannel(), False)
        req.setResponseCode(1)
        self.assertRaises(TypeError, req.setResponseCode, "1")

    def test_setResponseCodeAcceptsLongIntegers(self):
        """
        L{http.Request.setResponseCode} accepts L{int} for the code
        parameter.
        """
        req = http.Request(DummyChannel(), False)
        req.setResponseCode(1)

    def test_setLastModifiedNeverSet(self):
        """
        When no previous value was set and no 'if-modified-since' value was
        requested, L{http.Request.setLastModified} takes a timestamp in seconds
        since the epoch and sets the request's lastModified attribute.
        """
        req = http.Request(DummyChannel(), False)

        req.setLastModified(42)

        self.assertEqual(req.lastModified, 42)

    def test_setLastModifiedUpdate(self):
        """
        If the supplied timestamp is later than the lastModified attribute's
        value, L{http.Request.setLastModified} updates the lastModifed
        attribute.
        """
        req = http.Request(DummyChannel(), False)
        req.setLastModified(0)

        req.setLastModified(1)

        self.assertEqual(req.lastModified, 1)

    def test_setLastModifiedIgnore(self):
        """
        If the supplied timestamp occurs earlier than the current lastModified
        attribute, L{http.Request.setLastModified} ignores it.
        """
        req = http.Request(DummyChannel(), False)
        req.setLastModified(1)

        req.setLastModified(0)

        self.assertEqual(req.lastModified, 1)

    def test_setLastModifiedCached(self):
        """
        If the resource is older than the if-modified-since date in the request
        header, L{http.Request.setLastModified} returns L{http.CACHED}.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(
            networkString("if-modified-since"), [b"02 Jan 1970 00:00:00 GMT"]
        )

        result = req.setLastModified(42)

        self.assertEqual(result, http.CACHED)

    def test_setLastModifiedNotCached(self):
        """
        If the resource is newer than the if-modified-since date in the request
        header, L{http.Request.setLastModified} returns None
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(
            networkString("if-modified-since"), [b"01 Jan 1970 00:00:00 GMT"]
        )

        result = req.setLastModified(1000000)

        self.assertEqual(result, None)

    def test_setLastModifiedTwiceNotCached(self):
        """
        When L{http.Request.setLastModified} is called multiple times, the
        highest supplied value is honored. If that value is higher than the
        if-modified-since date in the request header, the method returns None.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(
            networkString("if-modified-since"), [b"01 Jan 1970 00:00:01 GMT"]
        )
        req.setLastModified(1000000)

        result = req.setLastModified(0)

        self.assertEqual(result, None)

    def test_setLastModifiedTwiceCached(self):
        """
        When L{http.Request.setLastModified} is called multiple times, the
        highest supplied value is honored. If that value is lower than the
        if-modified-since date in the request header, the method returns
        L{http.CACHED}.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(
            networkString("if-modified-since"), [b"01 Jan 1999 00:00:01 GMT"]
        )
        req.setLastModified(1)

        result = req.setLastModified(0)

        self.assertEqual(result, http.CACHED)

    def test_setHost(self):
        """
        L{http.Request.setHost} sets the value of the host request header.
        The port should not be added because it is the default.
        """
        req = http.Request(DummyChannel(), False)
        req.setHost(b"example.com", 80)
        self.assertEqual(req.requestHeaders.getRawHeaders(b"host"), [b"example.com"])

    def test_setHostSSL(self):
        """
        L{http.Request.setHost} sets the value of the host request header.
        The port should not be added because it is the default.
        """
        d = DummyChannel()
        d.transport = DummyChannel.SSL()
        req = http.Request(d, False)
        req.setHost(b"example.com", 443)
        self.assertEqual(req.requestHeaders.getRawHeaders(b"host"), [b"example.com"])

    def test_setHostNonDefaultPort(self):
        """
        L{http.Request.setHost} sets the value of the host request header.
        The port should be added because it is not the default.
        """
        req = http.Request(DummyChannel(), False)
        req.setHost(b"example.com", 81)
        self.assertEqual(req.requestHeaders.getRawHeaders(b"host"), [b"example.com:81"])

    def test_setHostSSLNonDefaultPort(self):
        """
        L{http.Request.setHost} sets the value of the host request header.
        The port should be added because it is not the default.
        """
        d = DummyChannel()
        d.transport = DummyChannel.SSL()
        req = http.Request(d, False)
        req.setHost(b"example.com", 81)
        self.assertEqual(req.requestHeaders.getRawHeaders(b"host"), [b"example.com:81"])

    def test_setHeader(self):
        """
        L{http.Request.setHeader} sets the value of the given response header.
        """
        req = http.Request(DummyChannel(), False)
        req.setHeader(b"test", b"lemur")
        self.assertEqual(req.responseHeaders.getRawHeaders(b"test"), [b"lemur"])

    def _checkCookie(self, expectedCookieValue, *args, **kwargs):
        """
        Call L{http.Request.addCookie} with C{*args} and C{**kwargs}, and check
        that the cookie value is equal to C{expectedCookieValue}.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        req.addCookie(*args, **kwargs)
        self.assertEqual(req.cookies[0], expectedCookieValue)

        # Write nothing to make it produce the headers
        req.write(b"")
        writtenLines = channel.transport.written.getvalue().split(b"\r\n")

        # There should be one Set-Cookie header
        addCookieLines = [x for x in writtenLines if x.startswith(b"Set-Cookie")]
        self.assertEqual(len(addCookieLines), 1)
        self.assertEqual(addCookieLines[0], b"Set-Cookie: " + expectedCookieValue)

    def test_addCookieWithMinimumArgumentsUnicode(self):
        """
        L{http.Request.addCookie} adds a new cookie to be sent with the
        response, and can be called with just a key and a value. L{unicode}
        arguments are encoded using UTF-8.
        """
        expectedCookieValue = b"foo=bar"

        self._checkCookie(expectedCookieValue, "foo", "bar")

    def test_addCookieWithAllArgumentsUnicode(self):
        """
        L{http.Request.addCookie} adds a new cookie to be sent with the
        response. L{unicode} arguments are encoded using UTF-8.
        """
        expectedCookieValue = (
            b"foo=bar; Expires=Fri, 31 Dec 9999 23:59:59 GMT; "
            b"Domain=.example.com; Path=/; Max-Age=31536000; "
            b"Comment=test; Secure; HttpOnly"
        )

        self._checkCookie(
            expectedCookieValue,
            "foo",
            "bar",
            expires="Fri, 31 Dec 9999 23:59:59 GMT",
            domain=".example.com",
            path="/",
            max_age="31536000",
            comment="test",
            secure=True,
            httpOnly=True,
        )

    def test_addCookieWithMinimumArgumentsBytes(self):
        """
        L{http.Request.addCookie} adds a new cookie to be sent with the
        response, and can be called with just a key and a value. L{bytes}
        arguments are not decoded.
        """
        expectedCookieValue = b"foo=bar"

        self._checkCookie(expectedCookieValue, b"foo", b"bar")

    def test_addCookieWithAllArgumentsBytes(self):
        """
        L{http.Request.addCookie} adds a new cookie to be sent with the
        response. L{bytes} arguments are not decoded.
        """
        expectedCookieValue = (
            b"foo=bar; Expires=Fri, 31 Dec 9999 23:59:59 GMT; "
            b"Domain=.example.com; Path=/; Max-Age=31536000; "
            b"Comment=test; Secure; HttpOnly"
        )

        self._checkCookie(
            expectedCookieValue,
            b"foo",
            b"bar",
            expires=b"Fri, 31 Dec 9999 23:59:59 GMT",
            domain=b".example.com",
            path=b"/",
            max_age=b"31536000",
            comment=b"test",
            secure=True,
            httpOnly=True,
        )

    def test_addCookieSanitization(self):
        """
        L{http.Request.addCookie} replaces linear whitespace and
        semicolons with single spaces.
        """

        def cookieValue(key, value):
            return b"=".join([key, value])

        arguments = [
            ("expires", b"Expires"),
            ("domain", b"Domain"),
            ("path", b"Path"),
            ("max_age", b"Max-Age"),
            ("comment", b"Comment"),
        ]

        inputsAndOutputs = list(
            zip(
                textLinearWhitespaceComponents + bytesLinearWhitespaceComponents,
                cycle([sanitizedBytes]),
            )
        )

        inputsAndOutputs = [
            ["Foo; bar", b"Foo  bar"],
            [b"Foo; bar", b"Foo  bar"],
        ]

        for inputValue, outputValue in inputsAndOutputs:
            self._checkCookie(
                cookieValue(outputValue, outputValue), inputValue, inputValue
            )
            for argument, parameter in arguments:
                expected = b"; ".join(
                    [
                        cookieValue(outputValue, outputValue),
                        cookieValue(parameter, outputValue),
                    ]
                )
                self._checkCookie(
                    expected, inputValue, inputValue, **{argument: inputValue}
                )

    def test_addCookieSameSite(self):
        """
        L{http.Request.setCookie} supports a C{sameSite} argument.
        """
        self._checkCookie(b"foo=bar; SameSite=lax", b"foo", b"bar", sameSite="lax")
        self._checkCookie(b"foo=bar; SameSite=lax", b"foo", b"bar", sameSite="Lax")
        self._checkCookie(
            b"foo=bar; SameSite=strict", b"foo", b"bar", sameSite="strict"
        )

        self.assertRaises(
            ValueError, self._checkCookie, b"", b"foo", b"bar", sameSite="anything-else"
        )

    def test_firstWrite(self):
        """
        For an HTTP 1.0 request, L{http.Request.write} sends an HTTP 1.0
        Response-Line and whatever response headers are set.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        trans = StringTransport()

        channel.transport = trans

        req.setResponseCode(200)
        req.clientproto = b"HTTP/1.0"
        req.responseHeaders.setRawHeaders(b"test", [b"lemur"])
        req.write(b"Hello")

        self.assertResponseEquals(
            trans.value(), [(b"HTTP/1.0 200 OK", b"Test: lemur", b"Hello")]
        )

    def test_firstWriteHTTP11Chunked(self):
        """
        For an HTTP 1.1 request, L{http.Request.write} sends an HTTP 1.1
        Response-Line, whatever response headers are set, and uses chunked
        encoding for the response body.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        trans = StringTransport()

        channel.transport = trans

        req.setResponseCode(200)
        req.clientproto = b"HTTP/1.1"
        req.responseHeaders.setRawHeaders(b"test", [b"lemur"])
        req.write(b"Hello")
        req.write(b"World!")

        self.assertResponseEquals(
            trans.value(),
            [
                (
                    b"HTTP/1.1 200 OK",
                    b"Test: lemur",
                    b"Transfer-Encoding: chunked",
                    b"5\r\nHello\r\n6\r\nWorld!\r\n",
                )
            ],
        )

    def test_firstWriteLastModified(self):
        """
        For an HTTP 1.0 request for a resource with a known last modified time,
        L{http.Request.write} sends an HTTP Response-Line, whatever response
        headers are set, and a last-modified header with that time.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        trans = StringTransport()

        channel.transport = trans

        req.setResponseCode(200)
        req.clientproto = b"HTTP/1.0"
        req.lastModified = 0
        req.responseHeaders.setRawHeaders(b"test", [b"lemur"])
        req.write(b"Hello")

        self.assertResponseEquals(
            trans.value(),
            [
                (
                    b"HTTP/1.0 200 OK",
                    b"Test: lemur",
                    b"Last-Modified: Thu, 01 Jan 1970 00:00:00 GMT",
                    b"Hello",
                )
            ],
        )

    def test_lastModifiedAlreadyWritten(self):
        """
        If the last-modified header already exists in the L{http.Request}
        response headers, the lastModified attribute is ignored and a message
        is logged.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)
        channel = DummyChannel()
        req = http.Request(channel, False)
        trans = StringTransport()

        channel.transport = trans

        req.setResponseCode(200)
        req.clientproto = b"HTTP/1.0"
        req.lastModified = 1000000000
        req.responseHeaders.setRawHeaders(
            b"last-modified", [b"Thu, 01 Jan 1970 00:00:00 GMT"]
        )
        req.write(b"Hello")

        self.assertResponseEquals(
            trans.value(),
            [
                (
                    b"HTTP/1.0 200 OK",
                    b"Last-Modified: Thu, 01 Jan 1970 00:00:00 GMT",
                    b"Hello",
                )
            ],
        )
        self.assertEquals(1, len(logObserver))
        event = logObserver[0]
        self.assertEquals(
            "Warning: last-modified specified both in"
            " header list and lastModified attribute.",
            event["log_format"],
        )

    def test_receivedCookiesDefault(self):
        """
        L{http.Request.received_cookies} defaults to an empty L{dict}.
        """
        req = http.Request(DummyChannel(), False)
        self.assertEqual(req.received_cookies, {})

    def test_parseCookies(self):
        """
        L{http.Request.parseCookies} extracts cookies from C{requestHeaders}
        and adds them to C{received_cookies}.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"cookie", [b'test="lemur"; test2="panda"'])
        req.parseCookies()
        self.assertEqual(
            req.received_cookies, {b"test": b'"lemur"', b"test2": b'"panda"'}
        )

    def test_parseCookiesMultipleHeaders(self):
        """
        L{http.Request.parseCookies} can extract cookies from multiple Cookie
        headers.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"cookie", [b'test="lemur"', b'test2="panda"'])
        req.parseCookies()
        self.assertEqual(
            req.received_cookies, {b"test": b'"lemur"', b"test2": b'"panda"'}
        )

    def test_parseCookiesNoCookie(self):
        """
        L{http.Request.parseCookies} can be called on a request without a
        cookie header.
        """
        req = http.Request(DummyChannel(), False)
        req.parseCookies()
        self.assertEqual(req.received_cookies, {})

    def test_parseCookiesEmptyCookie(self):
        """
        L{http.Request.parseCookies} can be called on a request with an
        empty cookie header.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"cookie", [])
        req.parseCookies()
        self.assertEqual(req.received_cookies, {})

    def test_parseCookiesIgnoreValueless(self):
        """
        L{http.Request.parseCookies} ignores cookies which don't have a
        value.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"cookie", [b"foo; bar; baz;"])
        req.parseCookies()
        self.assertEqual(req.received_cookies, {})

    def test_parseCookiesEmptyValue(self):
        """
        L{http.Request.parseCookies} parses cookies with an empty value.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"cookie", [b"foo="])
        req.parseCookies()
        self.assertEqual(req.received_cookies, {b"foo": b""})

    def test_parseCookiesRetainRightSpace(self):
        """
        L{http.Request.parseCookies} leaves trailing whitespace in the
        cookie value.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"cookie", [b"foo=bar "])
        req.parseCookies()
        self.assertEqual(req.received_cookies, {b"foo": b"bar "})

    def test_parseCookiesStripLeftSpace(self):
        """
        L{http.Request.parseCookies} strips leading whitespace in the
        cookie key.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(b"cookie", [b" foo=bar"])
        req.parseCookies()
        self.assertEqual(req.received_cookies, {b"foo": b"bar"})

    def test_parseCookiesContinueAfterMalformedCookie(self):
        """
        L{http.Request.parseCookies} parses valid cookies set before or
        after malformed cookies.
        """
        req = http.Request(DummyChannel(), False)
        req.requestHeaders.setRawHeaders(
            b"cookie", [b'12345; test="lemur"; 12345; test2="panda"; 12345']
        )
        req.parseCookies()
        self.assertEqual(
            req.received_cookies, {b"test": b'"lemur"', b"test2": b'"panda"'}
        )

    def test_connectionLost(self):
        """
        L{http.Request.connectionLost} closes L{Request.content} and drops the
        reference to the L{HTTPChannel} to assist with garbage collection.
        """
        req = http.Request(DummyChannel(), False)

        # Cause Request.content to be created at all.
        req.gotLength(10)

        # Grab a reference to content in case the Request drops it later on.
        content = req.content

        # Put some bytes into it
        req.handleContentChunk(b"hello")

        # Then something goes wrong and content should get closed.
        req.connectionLost(Failure(ConnectionLost("Finished")))
        self.assertTrue(content.closed)
        self.assertIdentical(req.channel, None)

    def test_registerProducerTwiceFails(self):
        """
        Calling L{Request.registerProducer} when a producer is already
        registered raises ValueError.
        """
        req = http.Request(DummyChannel(), False)
        req.registerProducer(DummyProducer(), True)
        self.assertRaises(ValueError, req.registerProducer, DummyProducer(), True)

    def test_registerProducerWhenNotQueuedRegistersPushProducer(self):
        """
        Calling L{Request.registerProducer} with an IPushProducer when the
        request is not queued registers the producer as a push producer on the
        request's transport.
        """
        req = http.Request(DummyChannel(), False)
        producer = DummyProducer()
        req.registerProducer(producer, True)
        self.assertEqual([(producer, True)], req.transport.producers)

    def test_registerProducerWhenNotQueuedRegistersPullProducer(self):
        """
        Calling L{Request.registerProducer} with an IPullProducer when the
        request is not queued registers the producer as a pull producer on the
        request's transport.
        """
        req = http.Request(DummyChannel(), False)
        producer = DummyProducer()
        req.registerProducer(producer, False)
        self.assertEqual([(producer, False)], req.transport.producers)

    def test_connectionLostNotification(self):
        """
        L{Request.connectionLost} triggers all finish notification Deferreds
        and cleans up per-request state.
        """
        d = DummyChannel()
        request = http.Request(d, True)
        finished = request.notifyFinish()
        request.connectionLost(Failure(ConnectionLost("Connection done")))
        self.assertIdentical(request.channel, None)
        return self.assertFailure(finished, ConnectionLost)

    def test_finishNotification(self):
        """
        L{Request.finish} triggers all finish notification Deferreds.
        """
        request = http.Request(DummyChannel(), False)
        finished = request.notifyFinish()
        # Force the request to have a non-None content attribute.  This is
        # probably a bug in Request.
        request.gotLength(1)
        request.finish()
        return finished

    def test_writeAfterFinish(self):
        """
        Calling L{Request.write} after L{Request.finish} has been called results
        in a L{RuntimeError} being raised.
        """
        request = http.Request(DummyChannel(), False)
        finished = request.notifyFinish()
        # Force the request to have a non-None content attribute.  This is
        # probably a bug in Request.
        request.gotLength(1)
        request.write(b"foobar")
        request.finish()
        self.assertRaises(RuntimeError, request.write, b"foobar")
        return finished

    def test_finishAfterConnectionLost(self):
        """
        Calling L{Request.finish} after L{Request.connectionLost} has been
        called results in a L{RuntimeError} being raised.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        req.connectionLost(Failure(ConnectionLost("The end.")))
        self.assertRaises(RuntimeError, req.finish)

    def test_writeAfterConnectionLost(self):
        """
        Calling L{Request.write} after L{Request.connectionLost} has been
        called does not raise an exception. L{RuntimeError} will be raised
        when finish is called on the request.
        """
        channel = DummyChannel()
        req = http.Request(channel, False)
        req.connectionLost(Failure(ConnectionLost("The end.")))
        req.write(b"foobar")
        self.assertRaises(RuntimeError, req.finish)

    def test_reprUninitialized(self):
        """
        L{Request.__repr__} returns the class name, object address, and
        dummy-place holder values when used on a L{Request} which has not yet
        been initialized.
        """
        request = http.Request(DummyChannel(), False)
        self.assertEqual(
            repr(request),
            "<Request at 0x%x method=(no method yet) uri=(no uri yet) "
            "clientproto=(no clientproto yet)>" % (id(request),),
        )

    def test_reprInitialized(self):
        """
        L{Request.__repr__} returns, as a L{str}, the class name, object
        address, and the method, uri, and client protocol of the HTTP request
        it represents.  The string is in the form::

          <Request at ADDRESS method=METHOD uri=URI clientproto=PROTOCOL>
        """
        request = http.Request(DummyChannel(), False)
        request.clientproto = b"HTTP/1.0"
        request.method = b"GET"
        request.uri = b"/foo/bar"
        self.assertEqual(
            repr(request),
            "<Request at 0x%x method=GET uri=/foo/bar "
            "clientproto=HTTP/1.0>" % (id(request),),
        )

    def test_reprSubclass(self):
        """
        Subclasses of L{Request} inherit a C{__repr__} implementation which
        includes the subclass's name in place of the string C{"Request"}.
        """

        class Otherwise(http.Request):
            pass

        request = Otherwise(DummyChannel(), False)
        self.assertEqual(
            repr(request),
            "<Otherwise at 0x%x method=(no method yet) uri=(no uri yet) "
            "clientproto=(no clientproto yet)>" % (id(request),),
        )

    def test_unregisterNonQueuedNonStreamingProducer(self):
        """
        L{Request.unregisterProducer} unregisters a non-queued non-streaming
        producer from the request and the request's transport.
        """
        req = http.Request(DummyChannel(), False)
        req.transport = StringTransport()
        req.registerProducer(DummyProducer(), False)
        req.unregisterProducer()
        self.assertEqual((None, None), (req.producer, req.transport.producer))

    def test_unregisterNonQueuedStreamingProducer(self):
        """
        L{Request.unregisterProducer} unregisters a non-queued streaming
        producer from the request and the request's transport.
        """
        req = http.Request(DummyChannel(), False)
        req.transport = StringTransport()
        req.registerProducer(DummyProducer(), True)
        req.unregisterProducer()
        self.assertEqual((None, None), (req.producer, req.transport.producer))

    def test_finishProducesLog(self):
        """
        L{http.Request.finish} will call the channel's factory to produce a log
        message.
        """
        factory = http.HTTPFactory()
        factory.timeOut = None
        factory._logDateTime = "sometime"
        factory._logDateTimeCall = True
        factory.startFactory()
        factory.logFile = BytesIO()
        proto = factory.buildProtocol(None)

        val = [b"GET /path HTTP/1.1\r\n", b"\r\n\r\n"]

        trans = StringTransport()
        proto.makeConnection(trans)

        for x in val:
            proto.dataReceived(x)

        proto._channel.requests[0].finish()

        # A log message should be written out
        self.assertIn(b'sometime "GET /path HTTP/1.1"', factory.logFile.getvalue())

    def test_requestBodyTimeoutFromFactory(self):
        """
        L{HTTPChannel} timeouts whenever data from a request body is not
        delivered to it in time, even when it gets built from a L{HTTPFactory}.
        """
        clock = Clock()
        factory = http.HTTPFactory(timeout=100, reactor=clock)
        factory.startFactory()
        protocol = factory.buildProtocol(None)
        transport = StringTransport()
        protocol = parametrizeTimeoutMixin(protocol, clock)

        # Confirm that the timeout is what we think it is.
        self.assertEqual(protocol.timeOut, 100)

        protocol.makeConnection(transport)
        protocol.dataReceived(b"POST / HTTP/1.0\r\nContent-Length: 2\r\n\r\n")
        clock.advance(99)
        self.assertFalse(transport.disconnecting)
        clock.advance(2)
        self.assertTrue(transport.disconnecting)

    def test_finishCleansConnection(self):
        """
        L{http.Request.finish} will notify the channel that it is finished, and
        will put the transport back in the producing state so that the reactor
        can close the connection.
        """
        factory = http.HTTPFactory()
        factory.timeOut = None
        factory._logDateTime = "sometime"
        factory._logDateTimeCall = True
        factory.startFactory()
        factory.logFile = BytesIO()
        proto = factory.buildProtocol(None)
        proto._channel._optimisticEagerReadSize = 0

        val = [b"GET /path HTTP/1.1\r\n", b"\r\n\r\n"]

        trans = StringTransport()
        proto.makeConnection(trans)

        self.assertEqual(trans.producerState, "producing")

        for x in val:
            proto.dataReceived(x)

        proto.dataReceived(b"GET ")  # just a few extra bytes to exhaust the
        # optimistic buffer size
        self.assertEqual(trans.producerState, "paused")
        proto._channel.requests[0].finish()
        self.assertEqual(trans.producerState, "producing")

    def test_provides_IDeprecatedHTTPChannelToRequestInterface(self):
        """
        L{http.Request} provides
        L{http._IDeprecatedHTTPChannelToRequestInterface}, which
        defines the interface used by L{http.HTTPChannel}.
        """
        req = http.Request(DummyChannel(), False)
        verifyObject(http._IDeprecatedHTTPChannelToRequestInterface, req)

    def test_eq(self):
        """
        A L{http.Request} is equal to itself.
        """
        req = http.Request(DummyChannel(), False)
        self.assertEqual(req, req)

    def test_ne(self):
        """
        A L{http.Request} is not equal to another object.
        """
        req = http.Request(DummyChannel(), False)
        self.assertNotEqual(req, http.Request(DummyChannel(), False))

    def test_hashable(self):
        """
        A L{http.Request} is hashable.
        """
        req = http.Request(DummyChannel(), False)
        hash(req)

    def test_eqWithNonRequest(self):
        """
        A L{http.Request} on the left hand side of an equality
        comparison to an instance that is not a L{http.Request} hands
        the comparison off to that object's C{__eq__} implementation.
        """
        eqCalls = []

        class _NotARequest:
            def __eq__(self, other: object) -> bool:
                eqCalls.append(other)
                return True

        req = http.Request(DummyChannel(), False)

        self.assertEqual(req, _NotARequest())
        self.assertEqual(eqCalls, [req])

    def test_neWithNonRequest(self):
        """
        A L{http.Request} on the left hand side of an inequality
        comparison to an instance that is not a L{http.Request} hands
        the comparison off to that object's C{__ne__} implementation.
        """
        eqCalls = []

        class _NotARequest:
            def __ne__(self, other: object) -> bool:
                eqCalls.append(other)
                return True

        req = http.Request(DummyChannel(), False)

        self.assertNotEqual(req, _NotARequest())
        self.assertEqual(eqCalls, [req])

    def test_finishProducerStillRegistered(self):
        """
        A RuntimeError is logged if a producer is still registered
        when an L{http.Request} is finished.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)
        request = http.Request(DummyChannel(), False)
        request.registerProducer(DummyProducer(), True)
        request.finish()
        self.assertEquals(1, len(logObserver))
        event = logObserver[0]
        f = event["log_failure"]
        self.assertIsInstance(f.value, RuntimeError)
        self.flushLoggedErrors(RuntimeError)

    def test_getClientIPWithIPv4(self):
        """
        L{http.Request.getClientIP} returns the host part of the
        client's address when connected over IPv4.
        """
        request = http.Request(
            DummyChannel(peer=address.IPv6Address("TCP", "127.0.0.1", 12344))
        )
        self.assertEqual(request.getClientIP(), "127.0.0.1")

    def test_getClientIPWithIPv6(self):
        """
        L{http.Request.getClientIP} returns the host part of the
        client's address when connected over IPv6.
        """
        request = http.Request(
            DummyChannel(peer=address.IPv6Address("TCP", "::1", 12344))
        )
        self.assertEqual(request.getClientIP(), "::1")

    def test_getClientIPWithNonTCPPeer(self):
        """
        L{http.Request.getClientIP} returns L{None} for the client's
        IP address when connected over a non-TCP transport.
        """
        request = http.Request(
            DummyChannel(peer=address.UNIXAddress("/path/to/socket"))
        )
        self.assertEqual(request.getClientIP(), None)

    def test_getClientAddress(self):
        """
        L{http.Request.getClientAddress} returns the client's address
        as an L{IAddress} provider.
        """
        client = address.UNIXAddress("/path/to/socket")
        request = http.Request(DummyChannel(peer=client))
        self.assertIs(request.getClientAddress(), client)


class MultilineHeadersTests(unittest.TestCase):
    """
    Tests to exercise handling of multiline headers by L{HTTPClient}.  RFCs 1945
    (HTTP 1.0) and 2616 (HTTP 1.1) state that HTTP message header fields can
    span multiple lines if each extra line is preceded by at least one space or
    horizontal tab.
    """

    def setUp(self):
        """
        Initialize variables used to verify that the header-processing functions
        are getting called.
        """
        self.handleHeaderCalled = False
        self.handleEndHeadersCalled = False

    # Dictionary of sample complete HTTP header key/value pairs, including
    # multiline headers.
    expectedHeaders = {
        b"Content-Length": b"10",
        b"X-Multiline": b"line-0\tline-1",
        b"X-Multiline2": b"line-2 line-3",
    }

    def ourHandleHeader(self, key, val):
        """
        Dummy implementation of L{HTTPClient.handleHeader}.
        """
        self.handleHeaderCalled = True
        self.assertEqual(val, self.expectedHeaders[key])

    def ourHandleEndHeaders(self):
        """
        Dummy implementation of L{HTTPClient.handleEndHeaders}.
        """
        self.handleEndHeadersCalled = True

    def test_extractHeader(self):
        """
        A header isn't processed by L{HTTPClient.extractHeader} until it is
        confirmed in L{HTTPClient.lineReceived} that the header has been
        received completely.
        """
        c = ClientDriver()
        c.handleHeader = self.ourHandleHeader
        c.handleEndHeaders = self.ourHandleEndHeaders

        c.lineReceived(b"HTTP/1.0 201")
        c.lineReceived(b"Content-Length: 10")
        self.assertIdentical(c.length, None)
        self.assertFalse(self.handleHeaderCalled)
        self.assertFalse(self.handleEndHeadersCalled)

        # Signal end of headers.
        c.lineReceived(b"")
        self.assertTrue(self.handleHeaderCalled)
        self.assertTrue(self.handleEndHeadersCalled)

        self.assertEqual(c.length, 10)

    def test_noHeaders(self):
        """
        An HTTP request with no headers will not cause any calls to
        L{handleHeader} but will cause L{handleEndHeaders} to be called on
        L{HTTPClient} subclasses.
        """
        c = ClientDriver()
        c.handleHeader = self.ourHandleHeader
        c.handleEndHeaders = self.ourHandleEndHeaders
        c.lineReceived(b"HTTP/1.0 201")

        # Signal end of headers.
        c.lineReceived(b"")
        self.assertFalse(self.handleHeaderCalled)
        self.assertTrue(self.handleEndHeadersCalled)

        self.assertEqual(c.version, b"HTTP/1.0")
        self.assertEqual(c.status, b"201")

    def test_multilineHeaders(self):
        """
        L{HTTPClient} parses multiline headers by buffering header lines until
        an empty line or a line that does not start with whitespace hits
        lineReceived, confirming that the header has been received completely.
        """
        c = ClientDriver()
        c.handleHeader = self.ourHandleHeader
        c.handleEndHeaders = self.ourHandleEndHeaders

        c.lineReceived(b"HTTP/1.0 201")
        c.lineReceived(b"X-Multiline: line-0")
        self.assertFalse(self.handleHeaderCalled)
        # Start continuing line with a tab.
        c.lineReceived(b"\tline-1")
        c.lineReceived(b"X-Multiline2: line-2")
        # The previous header must be complete, so now it can be processed.
        self.assertTrue(self.handleHeaderCalled)
        # Start continuing line with a space.
        c.lineReceived(b" line-3")
        c.lineReceived(b"Content-Length: 10")

        # Signal end of headers.
        c.lineReceived(b"")
        self.assertTrue(self.handleEndHeadersCalled)

        self.assertEqual(c.version, b"HTTP/1.0")
        self.assertEqual(c.status, b"201")
        self.assertEqual(c.length, 10)


class Expect100ContinueServerTests(unittest.TestCase, ResponseTestMixin):
    """
    Test that the HTTP server handles 'Expect: 100-continue' header correctly.

    The tests in this class all assume a simplistic behavior where user code
    cannot choose to deny a request. Once ticket #288 is implemented and user
    code can run before the body of a POST is processed this should be
    extended to support overriding this behavior.
    """

    def test_HTTP10(self):
        """
        HTTP/1.0 requests do not get 100-continue returned, even if 'Expect:
        100-continue' is included (RFC 2616 10.1.1).
        """
        transport = StringTransport()
        channel = http.HTTPChannel()
        channel.requestFactory = DummyHTTPHandlerProxy
        channel.makeConnection(transport)
        channel.dataReceived(b"GET / HTTP/1.0\r\n")
        channel.dataReceived(b"Host: www.example.com\r\n")
        channel.dataReceived(b"Content-Length: 3\r\n")
        channel.dataReceived(b"Expect: 100-continue\r\n")
        channel.dataReceived(b"\r\n")
        self.assertEqual(transport.value(), b"")
        channel.dataReceived(b"abc")
        self.assertResponseEquals(
            transport.value(),
            [
                (
                    b"HTTP/1.0 200 OK",
                    b"Command: GET",
                    b"Content-Length: 13",
                    b"Version: HTTP/1.0",
                    b"Request: /",
                    b"'''\n3\nabc'''\n",
                )
            ],
        )

    def test_expect100ContinueHeader(self):
        """
        If a HTTP/1.1 client sends a 'Expect: 100-continue' header, the server
        responds with a 100 response code before handling the request body, if
        any. The normal resource rendering code will then be called, which
        will send an additional response code.
        """
        transport = StringTransport()
        channel = http.HTTPChannel()
        channel.requestFactory = DummyHTTPHandlerProxy
        channel.makeConnection(transport)
        channel.dataReceived(b"GET / HTTP/1.1\r\n")
        channel.dataReceived(b"Host: www.example.com\r\n")
        channel.dataReceived(b"Expect: 100-continue\r\n")
        channel.dataReceived(b"Content-Length: 3\r\n")
        # The 100 continue response is not sent until all headers are
        # received:
        self.assertEqual(transport.value(), b"")
        channel.dataReceived(b"\r\n")
        # The 100 continue response is sent *before* the body is even
        # received:
        self.assertEqual(transport.value(), b"HTTP/1.1 100 Continue\r\n\r\n")
        channel.dataReceived(b"abc")
        response = transport.value()
        self.assertTrue(response.startswith(b"HTTP/1.1 100 Continue\r\n\r\n"))
        response = response[len(b"HTTP/1.1 100 Continue\r\n\r\n") :]
        self.assertResponseEquals(
            response,
            [
                (
                    b"HTTP/1.1 200 OK",
                    b"Command: GET",
                    b"Content-Length: 13",
                    b"Version: HTTP/1.1",
                    b"Request: /",
                    b"'''\n3\nabc'''\n",
                )
            ],
        )


def sub(keys, d):
    """
    Create a new dict containing only a subset of the items of an existing
    dict.

    @param keys: An iterable of the keys which will be added (with values from
        C{d}) to the result.

    @param d: The existing L{dict} from which to copy items.

    @return: The new L{dict} with keys given by C{keys} and values given by the
        corresponding values in C{d}.
    @rtype: L{dict}
    """
    return {k: d[k] for k in keys}


class DeprecatedRequestAttributesTests(unittest.TestCase):
    """
    Tests for deprecated attributes of L{twisted.web.http.Request}.
    """

    def test_getClientIP(self):
        """
        L{Request.getClientIP} is deprecated in favor of
        L{Request.getClientAddress}.
        """
        request = http.Request(
            DummyChannel(peer=address.IPv6Address("TCP", "127.0.0.1", 12345))
        )
        request.gotLength(0)
        request.requestReceived(b"GET", b"/", b"HTTP/1.1")
        request.getClientIP()

        warnings = self.flushWarnings(offendingFunctions=[self.test_getClientIP])

        self.assertEqual(1, len(warnings))
        self.assertEqual(
            {
                "category": DeprecationWarning,
                "message": (
                    "twisted.web.http.Request.getClientIP was deprecated "
                    "in Twisted 18.4.0; please use getClientAddress instead"
                ),
            },
            sub(["category", "message"], warnings[0]),
        )

    def test_noLongerQueued(self):
        """
        L{Request.noLongerQueued} is deprecated, as we no longer process
        requests simultaneously.
        """
        channel = DummyChannel()
        request = http.Request(channel)
        request.noLongerQueued()

        warnings = self.flushWarnings(offendingFunctions=[self.test_noLongerQueued])

        self.assertEqual(1, len(warnings))
        self.assertEqual(
            {
                "category": DeprecationWarning,
                "message": (
                    "twisted.web.http.Request.noLongerQueued was deprecated "
                    "in Twisted 16.3.0"
                ),
            },
            sub(["category", "message"], warnings[0]),
        )


class ChannelProductionTests(unittest.TestCase):
    """
    Tests for the way HTTPChannel manages backpressure.
    """

    request = b"GET / HTTP/1.1\r\n" b"Host: localhost\r\n" b"\r\n"

    def buildChannelAndTransport(self, transport, requestFactory):
        """
        Setup a L{HTTPChannel} and a transport and associate them.

        @param transport: A transport to back the L{HTTPChannel}
        @param requestFactory: An object that can construct L{Request} objects.
        @return: A tuple of the channel and the transport.
        """
        transport = transport
        channel = http.HTTPChannel()
        channel.requestFactory = _makeRequestProxyFactory(requestFactory)
        channel.makeConnection(transport)

        return channel, transport

    def test_HTTPChannelIsAProducer(self):
        """
        L{HTTPChannel} registers itself as a producer with its transport when a
        connection is made.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DummyHTTPHandler
        )

        self.assertEqual(transport.producer, channel)
        self.assertTrue(transport.streaming)

    def test_HTTPChannelUnregistersSelfWhenCallingLoseConnection(self):
        """
        L{HTTPChannel} unregisters itself when it has loseConnection called.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DummyHTTPHandler
        )
        channel.loseConnection()

        self.assertIs(transport.producer, None)
        self.assertIs(transport.streaming, None)

    def test_HTTPChannelRejectsMultipleProducers(self):
        """
        If two producers are registered on a L{HTTPChannel} without the first
        being unregistered, a L{RuntimeError} is thrown.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DummyHTTPHandler
        )

        channel.registerProducer(DummyProducer(), True)
        self.assertRaises(RuntimeError, channel.registerProducer, DummyProducer(), True)

    def test_HTTPChannelCanUnregisterWithNoProducer(self):
        """
        If there is no producer, the L{HTTPChannel} can still have
        C{unregisterProducer} called.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DummyHTTPHandler
        )

        channel.unregisterProducer()
        self.assertIs(channel._requestProducer, None)

    def test_HTTPChannelStopWithNoRequestOutstanding(self):
        """
        If there is no request producer currently registered, C{stopProducing}
        does nothing.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DummyHTTPHandler
        )

        channel.unregisterProducer()
        self.assertIs(channel._requestProducer, None)

    def test_HTTPChannelStopRequestProducer(self):
        """
        If there is a request producer registered with L{HTTPChannel}, calling
        C{stopProducing} causes that producer to be stopped as well.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DelayedHTTPHandler
        )

        # Feed a request in to spawn a Request object, then grab it.
        channel.dataReceived(self.request)
        request = channel.requests[0].original

        # Register a dummy producer.
        producer = DummyProducer()
        request.registerProducer(producer, True)

        # The dummy producer is currently unpaused.
        self.assertEqual(producer.events, [])

        # The transport now stops production. This stops the request producer.
        channel.stopProducing()
        self.assertEqual(producer.events, ["stop"])

    def test_HTTPChannelPropagatesProducingFromTransportToTransport(self):
        """
        When L{HTTPChannel} has C{pauseProducing} called on it by the transport
        it will call C{pauseProducing} on the transport. When unpaused, the
        L{HTTPChannel} will call C{resumeProducing} on its transport.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DummyHTTPHandler
        )

        # The transport starts in producing state.
        self.assertEqual(transport.producerState, "producing")

        # Pause producing. The transport should now be paused as well.
        channel.pauseProducing()
        self.assertEqual(transport.producerState, "paused")

        # Resume producing. The transport should be unpaused.
        channel.resumeProducing()
        self.assertEqual(transport.producerState, "producing")

    def test_HTTPChannelPropagatesPausedProductionToRequest(self):
        """
        If a L{Request} object has registered itself as a producer with a
        L{HTTPChannel} object, and the L{HTTPChannel} object is paused, both
        the transport and L{Request} objects get paused.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DelayedHTTPHandler
        )
        channel._optimisticEagerReadSize = 0

        # Feed a request in to spawn a Request object, then grab it.
        channel.dataReceived(self.request)
        # A little extra data to pause the transport.
        channel.dataReceived(b"123")
        request = channel.requests[0].original

        # Register a dummy producer.
        producer = DummyProducer()
        request.registerProducer(producer, True)

        # Note that the transport is paused while it waits for a response.
        # The dummy producer, however, is unpaused.
        self.assertEqual(transport.producerState, "paused")
        self.assertEqual(producer.events, [])

        # The transport now pauses production. This causes the producer to be
        # paused. The transport stays paused.
        channel.pauseProducing()
        self.assertEqual(transport.producerState, "paused")
        self.assertEqual(producer.events, ["pause"])

        # The transport has become unblocked and resumes production. This
        # unblocks the dummy producer, but leaves the transport blocked.
        channel.resumeProducing()
        self.assertEqual(transport.producerState, "paused")
        self.assertEqual(producer.events, ["pause", "resume"])

        # Unregister the producer and then complete the response. Because the
        # channel is not paused, the transport now gets unpaused.
        request.unregisterProducer()
        request.delayedProcess()
        self.assertEqual(transport.producerState, "producing")

    def test_HTTPChannelStaysPausedWhenRequestCompletes(self):
        """
        If a L{Request} object completes its response while the transport is
        paused, the L{HTTPChannel} does not resume the transport.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DelayedHTTPHandler
        )

        channel._optimisticEagerReadSize = 0

        # Feed a request in to spawn a Request object, then grab it.
        channel.dataReceived(self.request)
        channel.dataReceived(b"extra")  # exceed buffer size to pause the
        # transport.
        request = channel.requests[0].original

        # Register a dummy producer.
        producer = DummyProducer()
        request.registerProducer(producer, True)

        # Note that the transport is paused while it waits for a response.
        # The dummy producer, however, is unpaused.
        self.assertEqual(transport.producerState, "paused")
        self.assertEqual(producer.events, [])

        # The transport now pauses production. This causes the producer to be
        # paused. The transport stays paused.
        channel.pauseProducing()
        self.assertEqual(transport.producerState, "paused")
        self.assertEqual(producer.events, ["pause"])

        # Unregister the producer and then complete the response. Because the
        # channel is still paused, the transport stays paused
        request.unregisterProducer()
        request.delayedProcess()
        self.assertEqual(transport.producerState, "paused")

        # At this point the channel is resumed, and so is the transport.
        channel.resumeProducing()
        self.assertEqual(transport.producerState, "producing")

    def test_HTTPChannelToleratesDataWhenTransportPaused(self):
        """
        If the L{HTTPChannel} has paused the transport, it still tolerates
        receiving data, and does not attempt to pause the transport again.
        """

        class NoDoublePauseTransport(StringTransport):
            """
            A version of L{StringTransport} that fails tests if it is paused
            while already paused.
            """

            def pauseProducing(self):
                if self.producerState == "paused":
                    raise RuntimeError("Transport was paused twice!")
                StringTransport.pauseProducing(self)

        # Confirm that pausing a NoDoublePauseTransport twice fails.
        transport = NoDoublePauseTransport()
        transport.pauseProducing()
        self.assertRaises(RuntimeError, transport.pauseProducing)

        channel, transport = self.buildChannelAndTransport(
            NoDoublePauseTransport(), DummyHTTPHandler
        )

        # The transport starts in producing state.
        self.assertEqual(transport.producerState, "producing")

        # Pause producing. The transport should now be paused as well.
        channel.pauseProducing()
        self.assertEqual(transport.producerState, "paused")

        # Write in a request, even though the transport is paused.
        channel.dataReceived(self.request)

        # The transport is still paused, but we have tried to write the
        # response out.
        self.assertEqual(transport.producerState, "paused")
        self.assertTrue(transport.value().startswith(b"HTTP/1.1 200 OK\r\n"))

        # Resume producing. The transport should be unpaused.
        channel.resumeProducing()
        self.assertEqual(transport.producerState, "producing")

    def test_HTTPChannelToleratesPullProducers(self):
        """
        If the L{HTTPChannel} has a L{IPullProducer} registered with it it can
        adapt that producer into an L{IPushProducer}.
        """
        channel, transport = self.buildChannelAndTransport(
            StringTransport(), DummyPullProducerHandler
        )
        transport = StringTransport()
        channel = http.HTTPChannel()
        channel.requestFactory = DummyPullProducerHandlerProxy
        channel.makeConnection(transport)

        channel.dataReceived(self.request)
        request = channel.requests[0].original
        responseComplete = request._actualProducer.result

        def validate(ign):
            responseBody = transport.value().split(b"\r\n\r\n", 1)[1]
            expectedResponseBody = (
                b"1\r\n0\r\n"
                b"1\r\n1\r\n"
                b"1\r\n2\r\n"
                b"1\r\n3\r\n"
                b"1\r\n4\r\n"
                b"1\r\n5\r\n"
                b"1\r\n6\r\n"
                b"1\r\n7\r\n"
                b"1\r\n8\r\n"
                b"1\r\n9\r\n"
            )
            self.assertEqual(responseBody, expectedResponseBody)

        return responseComplete.addCallback(validate)

    def test_HTTPChannelUnregistersSelfWhenTimingOut(self):
        """
        L{HTTPChannel} unregisters itself when it times out a connection.
        """
        clock = Clock()
        transport = StringTransport()
        channel = http.HTTPChannel()

        # Patch the channel's callLater method.
        channel.timeOut = 100
        channel.callLater = clock.callLater
        channel.makeConnection(transport)

        # Tick the clock forward almost to the timeout.
        clock.advance(99)
        self.assertIs(transport.producer, channel)
        self.assertIs(transport.streaming, True)

        # Fire the timeout.
        clock.advance(1)
        self.assertIs(transport.producer, None)
        self.assertIs(transport.streaming, None)


class HTTPChannelSanitizationTests(unittest.SynchronousTestCase):
    """
    Test that L{HTTPChannel} sanitizes its output.
    """

    def test_writeHeadersSanitizesLinearWhitespace(self):
        """
        L{HTTPChannel.writeHeaders} removes linear whitespace from the
        list of header names and values it receives.
        """
        for component in bytesLinearWhitespaceComponents:
            transport = StringTransport()
            channel = http.HTTPChannel()
            channel.makeConnection(transport)

            channel.writeHeaders(
                version=b"HTTP/1.1",
                code=b"200",
                reason=b"OK",
                headers=[(component, component)],
            )

            sanitizedHeaderLine = (
                b": ".join(
                    [
                        sanitizedBytes,
                        sanitizedBytes,
                    ]
                )
                + b"\r\n"
            )

            self.assertEqual(
                transport.value(),
                b"\r\n".join(
                    [
                        b"HTTP/1.1 200 OK",
                        sanitizedHeaderLine,
                        b"",
                    ]
                ),
            )


class HTTPClientSanitizationTests(unittest.SynchronousTestCase):
    """
    Test that L{http.HTTPClient} sanitizes its output.
    """

    def test_sendHeaderSanitizesLinearWhitespace(self):
        """
        L{HTTPClient.sendHeader} replaces linear whitespace in its
        header keys and values with a single space.
        """
        for component in bytesLinearWhitespaceComponents:
            transport = StringTransport()
            client = http.HTTPClient()
            client.makeConnection(transport)
            client.sendHeader(component, component)
            self.assertEqual(
                transport.value().splitlines(),
                [b": ".join([sanitizedBytes, sanitizedBytes])],
            )


class HexHelperTests(unittest.SynchronousTestCase):
    """
    Test the L{http._hexint} and L{http._ishexdigits} helper functions.
    """

    badStrings = (b"", b"0x1234", b"feds", b"-123" b"+123")

    def test_isHex(self):
        """
        L{_ishexdigits()} returns L{True} for nonempy bytestrings containing
        hexadecimal digits.
        """
        for s in (b"10", b"abcdef", b"AB1234", b"fed", b"123467890"):
            self.assertIs(True, http._ishexdigits(s))

    def test_decodes(self):
        """
        L{_hexint()} returns the integer equivalent of the input.
        """
        self.assertEqual(10, http._hexint(b"a"))
        self.assertEqual(0x10, http._hexint(b"10"))
        self.assertEqual(0xABCD123, http._hexint(b"abCD123"))

    def test_isNotHex(self):
        """
        L{_ishexdigits()} returns L{False} for bytestrings that don't contain
        hexadecimal digits, including the empty string.
        """
        for s in self.badStrings:
            self.assertIs(False, http._ishexdigits(s))

    def test_decodeNotHex(self):
        """
        L{_hexint()} raises L{ValueError} for bytestrings that can't
        be decoded.
        """
        for s in self.badStrings:
            self.assertRaises(ValueError, http._hexint, s)
