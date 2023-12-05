# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{ITLSTransport}.
"""


from typing import Optional, Sequence, Type

from zope.interface import Interface, implementer

from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.endpoints import (
    SSL4ClientEndpoint,
    SSL4ServerEndpoint,
    TCP4ClientEndpoint,
)
from twisted.internet.error import ConnectionClosed
from twisted.internet.interfaces import (
    IReactorSSL,
    IStreamClientEndpoint,
    ITLSTransport,
)
from twisted.internet.protocol import ClientFactory, Protocol, ServerFactory
from twisted.internet.task import Cooperator
from twisted.internet.test.connectionmixins import (
    BrokenContextFactory,
    ConnectionTestsMixin,
    EndpointCreator,
)
from twisted.internet.test.reactormixins import ReactorBuilder
from twisted.internet.test.test_tcp import (
    AbortConnectionMixin,
    ConnectToTCPListenerMixin,
    StreamTransportTestsMixin,
)
from twisted.python.compat import networkString
from twisted.python.filepath import FilePath
from twisted.python.runtime import platform
from twisted.trial.unittest import SkipTest

try:
    from OpenSSL.crypto import FILETYPE_PEM
except ImportError:
    FILETYPE_PEM = None  # type: ignore[assignment]
else:
    from twisted.internet.ssl import ClientContextFactory, KeyPair, PrivateCertificate


class TLSMixin:
    requiredInterfaces: Optional[Sequence[Type[Interface]]] = [IReactorSSL]

    if platform.isWindows():
        msg = (
            "For some reason, these reactors don't deal with SSL "
            "disconnection correctly on Windows.  See #3371."
        )
        skippedReactors = {
            "twisted.internet.glib2reactor.Glib2Reactor": msg,
            "twisted.internet.gtk2reactor.Gtk2Reactor": msg,
        }


class ContextGeneratingMixin:
    import twisted

    _pem = (
        FilePath(networkString(twisted.__file__)).sibling(b"test").child(b"server.pem")
    )
    del twisted

    def getServerContext(self):
        """
        Return a new SSL context suitable for use in a test server.
        """
        pem = self._pem.getContent()
        cert = PrivateCertificate.load(
            pem, KeyPair.load(pem, FILETYPE_PEM), FILETYPE_PEM
        )
        return cert.options()

    def getClientContext(self):
        return ClientContextFactory()


@implementer(IStreamClientEndpoint)
class StartTLSClientEndpoint:
    """
    An endpoint which wraps another one and adds a TLS layer immediately when
    connections are set up.

    @ivar wrapped: A L{IStreamClientEndpoint} provider which will be used to
        really set up connections.

    @ivar contextFactory: A L{ContextFactory} to use to do TLS.
    """

    def __init__(self, wrapped, contextFactory):
        self.wrapped = wrapped
        self.contextFactory = contextFactory

    def connect(self, factory):
        """
        Establish a connection using a protocol build by C{factory} and
        immediately start TLS on it.  Return a L{Deferred} which fires with the
        protocol instance.
        """
        # This would be cleaner when we have ITransport.switchProtocol, which
        # will be added with ticket #3204:
        class WrapperFactory(ServerFactory):
            def buildProtocol(wrapperSelf, addr):
                protocol = factory.buildProtocol(addr)

                def connectionMade(orig=protocol.connectionMade):
                    protocol.transport.startTLS(self.contextFactory)
                    orig()

                protocol.connectionMade = connectionMade
                return protocol

        return self.wrapped.connect(WrapperFactory())


class StartTLSClientCreator(EndpointCreator, ContextGeneratingMixin):
    """
    Create L{ITLSTransport.startTLS} endpoint for the client, and normal SSL
    for server just because it's easier.
    """

    def server(self, reactor):
        """
        Construct an SSL server endpoint.  This should be constructing a TCP
        server endpoint which immediately calls C{startTLS} instead, but that
        is hard.
        """
        return SSL4ServerEndpoint(reactor, 0, self.getServerContext())

    def client(self, reactor, serverAddress):
        """
        Construct a TCP client endpoint wrapped to immediately start TLS.
        """
        return StartTLSClientEndpoint(
            TCP4ClientEndpoint(reactor, "127.0.0.1", serverAddress.port),
            ClientContextFactory(),
        )


class BadContextTestsMixin:
    """
    Mixin for L{ReactorBuilder} subclasses which defines a helper for testing
    the handling of broken context factories.
    """

    def _testBadContext(self, useIt):
        """
        Assert that the exception raised by a broken context factory's
        C{getContext} method is raised by some reactor method.  If it is not, an
        exception will be raised to fail the test.

        @param useIt: A two-argument callable which will be called with a
            reactor and a broken context factory and which is expected to raise
            the same exception as the broken context factory's C{getContext}
            method.
        """
        reactor = self.buildReactor()
        exc = self.assertRaises(ValueError, useIt, reactor, BrokenContextFactory())
        self.assertEqual(BrokenContextFactory.message, str(exc))


class StartTLSClientTestsMixin(TLSMixin, ReactorBuilder, ConnectionTestsMixin):
    """
    Tests for TLS connections established using L{ITLSTransport.startTLS} (as
    opposed to L{IReactorSSL.connectSSL} or L{IReactorSSL.listenSSL}).
    """

    endpoints = StartTLSClientCreator()


class SSLCreator(EndpointCreator, ContextGeneratingMixin):
    """
    Create SSL endpoints.
    """

    def server(self, reactor):
        """
        Create an SSL server endpoint on a TCP/IP-stack allocated port.
        """
        return SSL4ServerEndpoint(reactor, 0, self.getServerContext())

    def client(self, reactor, serverAddress):
        """
        Create an SSL client endpoint which will connect localhost on
        the port given by C{serverAddress}.

        @type serverAddress: L{IPv4Address}
        """
        return SSL4ClientEndpoint(
            reactor, "127.0.0.1", serverAddress.port, ClientContextFactory()
        )


class SSLClientTestsMixin(
    TLSMixin,
    ReactorBuilder,
    ContextGeneratingMixin,
    ConnectionTestsMixin,
    BadContextTestsMixin,
):
    """
    Mixin defining tests relating to L{ITLSTransport}.
    """

    endpoints = SSLCreator()

    def test_badContext(self):
        """
        If the context factory passed to L{IReactorSSL.connectSSL} raises an
        exception from its C{getContext} method, that exception is raised by
        L{IReactorSSL.connectSSL}.
        """

        def useIt(reactor, contextFactory):
            return reactor.connectSSL(
                "127.0.0.1", 1234, ClientFactory(), contextFactory
            )

        self._testBadContext(useIt)

    def test_disconnectAfterWriteAfterStartTLS(self):
        """
        L{ITCPTransport.loseConnection} ends a connection which was set up with
        L{ITLSTransport.startTLS} and which has recently been written to.  This
        is intended to verify that a socket send error masked by the TLS
        implementation doesn't prevent the connection from being reported as
        closed.
        """

        class ShortProtocol(Protocol):
            def connectionMade(self):
                if not ITLSTransport.providedBy(self.transport):
                    # Functionality isn't available to be tested.
                    finished = self.factory.finished
                    self.factory.finished = None
                    finished.errback(SkipTest("No ITLSTransport support"))
                    return

                # Switch the transport to TLS.
                self.transport.startTLS(self.factory.context)
                # Force TLS to really get negotiated.  If nobody talks, nothing
                # will happen.
                self.transport.write(b"x")

            def dataReceived(self, data):
                # Stuff some bytes into the socket.  This mostly has the effect
                # of causing the next write to fail with ENOTCONN or EPIPE.
                # With the pyOpenSSL implementation of ITLSTransport, the error
                # is swallowed outside of the control of Twisted.
                self.transport.write(b"y")
                # Now close the connection, which requires a TLS close alert to
                # be sent.
                self.transport.loseConnection()

            def connectionLost(self, reason):
                # This is the success case.  The client and the server want to
                # get here.
                finished = self.factory.finished
                if finished is not None:
                    self.factory.finished = None
                    finished.callback(reason)

        reactor = self.buildReactor()

        serverFactory = ServerFactory()
        serverFactory.finished = Deferred()
        serverFactory.protocol = ShortProtocol
        serverFactory.context = self.getServerContext()

        clientFactory = ClientFactory()
        clientFactory.finished = Deferred()
        clientFactory.protocol = ShortProtocol
        clientFactory.context = self.getClientContext()
        clientFactory.context.method = serverFactory.context.method

        lostConnectionResults = []
        finished = DeferredList(
            [serverFactory.finished, clientFactory.finished], consumeErrors=True
        )

        def cbFinished(results):
            lostConnectionResults.extend([results[0][1], results[1][1]])

        finished.addCallback(cbFinished)

        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        connector = reactor.connectTCP(
            port.getHost().host, port.getHost().port, clientFactory
        )
        self.addCleanup(connector.disconnect)

        finished.addCallback(lambda ign: reactor.stop())
        self.runReactor(reactor)
        lostConnectionResults[0].trap(ConnectionClosed)
        lostConnectionResults[1].trap(ConnectionClosed)


class TLSPortTestsBuilder(
    TLSMixin,
    ContextGeneratingMixin,
    BadContextTestsMixin,
    ConnectToTCPListenerMixin,
    StreamTransportTestsMixin,
    ReactorBuilder,
):
    """
    Tests for L{IReactorSSL.listenSSL}
    """

    def getListeningPort(self, reactor, factory):
        """
        Get a TLS port from a reactor.
        """
        return reactor.listenSSL(0, factory, self.getServerContext())

    def getExpectedStartListeningLogMessage(self, port, factory):
        """
        Get the message expected to be logged when a TLS port starts listening.
        """
        return "%s (TLS) starting on %d" % (factory, port.getHost().port)

    def getExpectedConnectionLostLogMsg(self, port):
        """
        Get the expected connection lost message for a TLS port.
        """
        return f"(TLS Port {port.getHost().port} Closed)"

    def test_badContext(self):
        """
        If the context factory passed to L{IReactorSSL.listenSSL} raises an
        exception from its C{getContext} method, that exception is raised by
        L{IReactorSSL.listenSSL}.
        """

        def useIt(reactor, contextFactory):
            return reactor.listenSSL(0, ServerFactory(), contextFactory)

        self._testBadContext(useIt)

    def connectToListener(self, reactor, address, factory):
        """
        Connect to the given listening TLS port, assuming the
        underlying transport is TCP.

        @param reactor: The reactor under test.
        @type reactor: L{IReactorSSL}

        @param address: The listening's address.  Only the C{port}
            component is used; see
            L{ConnectToTCPListenerMixin.LISTENER_HOST}.
        @type address: L{IPv4Address} or L{IPv6Address}

        @param factory: The client factory.
        @type factory: L{ClientFactory}

        @return: The connector
        """
        return reactor.connectSSL(
            self.LISTENER_HOST,
            address.port,
            factory,
            self.getClientContext(),
        )


globals().update(SSLClientTestsMixin.makeTestCaseClasses())
globals().update(StartTLSClientTestsMixin.makeTestCaseClasses())
globals().update(TLSPortTestsBuilder().makeTestCaseClasses())


class AbortSSLConnectionTests(
    ReactorBuilder, AbortConnectionMixin, ContextGeneratingMixin
):
    """
    C{abortConnection} tests using SSL.
    """

    requiredInterfaces = (IReactorSSL,)
    endpoints = SSLCreator()

    def buildReactor(self):
        reactor = ReactorBuilder.buildReactor(self)
        from twisted.internet import _producer_helpers

        # Patch twisted.protocols.tls to use this reactor, until we get
        # around to fixing #5206, or the TLS code uses an explicit reactor:
        cooperator = Cooperator(scheduler=lambda x: reactor.callLater(0.00001, x))
        self.patch(_producer_helpers, "cooperate", cooperator.cooperate)
        return reactor

    def setUp(self):
        if FILETYPE_PEM is None:
            raise SkipTest("OpenSSL not available.")


globals().update(AbortSSLConnectionTests.makeTestCaseClasses())
