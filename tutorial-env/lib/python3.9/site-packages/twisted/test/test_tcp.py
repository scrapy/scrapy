# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorTCP}.
"""


import errno
import random
import socket
from functools import wraps
from typing import Callable, Optional
from unittest import skipIf

from zope.interface import implementer

import hamcrest

from twisted.internet import defer, error, interfaces, protocol, reactor
from twisted.internet.address import IPv4Address
from twisted.internet.interfaces import IHalfCloseableProtocol, IPullProducer
from twisted.internet.protocol import Protocol
from twisted.protocols import policies
from twisted.python.log import err, msg
from twisted.python.runtime import platform
from twisted.test.proto_helpers import AccumulatingProtocol
from twisted.trial.unittest import SkipTest, TestCase


def loopUntil(predicate, interval=0):
    """
    Poor excuse for an event notification helper.  This polls a condition and
    calls back a Deferred when it is seen to be true.

    Do not use this function.
    """
    from twisted.internet import task

    d = defer.Deferred()

    def check():
        res = predicate()
        if res:
            d.callback(res)

    call = task.LoopingCall(check)

    def stop(result):
        call.stop()
        return result

    d.addCallback(stop)
    d2 = call.start(interval)
    d2.addErrback(d.errback)
    return d


class ClosingProtocol(protocol.Protocol):
    def connectionMade(self):
        msg("ClosingProtocol.connectionMade")
        self.transport.loseConnection()

    def connectionLost(self, reason):
        msg("ClosingProtocol.connectionLost")
        reason.trap(error.ConnectionDone)


class ClosingFactory(protocol.ServerFactory):
    """
    Factory that closes port immediately.
    """

    _cleanerUpper = None

    def buildProtocol(self, conn):
        self._cleanerUpper = self.port.stopListening()
        return ClosingProtocol()

    def cleanUp(self):
        """
        Clean-up for tests to wait for the port to stop listening.
        """
        if self._cleanerUpper is None:
            return self.port.stopListening()
        return self._cleanerUpper


class MyProtocolFactoryMixin:
    """
    Mixin for factories which create L{AccumulatingProtocol} instances.

    @type protocolFactory: no-argument callable
    @ivar protocolFactory: Factory for protocols - takes the place of the
        typical C{protocol} attribute of factories (but that name is used by
        this class for something else).

    @type protocolConnectionMade: L{None} or L{defer.Deferred}
    @ivar protocolConnectionMade: When an instance of L{AccumulatingProtocol}
        is connected, if this is not L{None}, the L{Deferred} will be called
        back with the protocol instance and the attribute set to L{None}.

    @type protocolConnectionLost: L{None} or L{defer.Deferred}
    @ivar protocolConnectionLost: When an instance of L{AccumulatingProtocol}
        is created, this will be set as its C{closedDeferred} attribute and
        then this attribute will be set to L{None} so the L{defer.Deferred} is
        not used by more than one protocol.

    @ivar protocol: The most recently created L{AccumulatingProtocol} instance
        which was returned from C{buildProtocol}.

    @type called: C{int}
    @ivar called: A counter which is incremented each time C{buildProtocol}
        is called.

    @ivar peerAddresses: A C{list} of the addresses passed to C{buildProtocol}.
    """

    protocolFactory = AccumulatingProtocol

    protocolConnectionMade = None
    protocolConnectionLost = None
    protocol: Optional[Callable[[], Protocol]] = None
    called = 0

    def __init__(self):
        self.peerAddresses = []

    def buildProtocol(self, addr):
        """
        Create a L{AccumulatingProtocol} and set it up to be able to perform
        callbacks.
        """
        self.peerAddresses.append(addr)
        self.called += 1
        p = self.protocolFactory()
        p.factory = self
        p.closedDeferred = self.protocolConnectionLost
        self.protocolConnectionLost = None
        self.protocol = p
        return p


class MyServerFactory(MyProtocolFactoryMixin, protocol.ServerFactory):
    """
    Server factory which creates L{AccumulatingProtocol} instances.
    """


class MyClientFactory(MyProtocolFactoryMixin, protocol.ClientFactory):
    """
    Client factory which creates L{AccumulatingProtocol} instances.
    """

    failed = 0
    stopped = 0

    def __init__(self):
        MyProtocolFactoryMixin.__init__(self)
        self.deferred = defer.Deferred()
        self.failDeferred = defer.Deferred()

    def clientConnectionFailed(self, connector, reason):
        self.failed = 1
        self.reason = reason
        self.failDeferred.callback(None)

    def clientConnectionLost(self, connector, reason):
        self.lostReason = reason
        self.deferred.callback(None)

    def stopFactory(self):
        self.stopped = 1


class ListeningTests(TestCase):
    def test_listen(self):
        """
        L{IReactorTCP.listenTCP} returns an object which provides
        L{IListeningPort}.
        """
        f = MyServerFactory()
        p1 = reactor.listenTCP(0, f, interface="127.0.0.1")
        self.addCleanup(p1.stopListening)
        self.assertTrue(interfaces.IListeningPort.providedBy(p1))

    def testStopListening(self):
        """
        The L{IListeningPort} returned by L{IReactorTCP.listenTCP} can be
        stopped with its C{stopListening} method.  After the L{Deferred} it
        (optionally) returns has been called back, the port number can be bound
        to a new server.
        """
        f = MyServerFactory()
        port = reactor.listenTCP(0, f, interface="127.0.0.1")
        n = port.getHost().port

        def cbStopListening(ignored):
            # Make sure we can rebind the port right away
            port = reactor.listenTCP(n, f, interface="127.0.0.1")
            return port.stopListening()

        d = defer.maybeDeferred(port.stopListening)
        d.addCallback(cbStopListening)
        return d

    def testNumberedInterface(self):
        f = MyServerFactory()
        # listen only on the loopback interface
        p1 = reactor.listenTCP(0, f, interface="127.0.0.1")
        return p1.stopListening()

    def testPortRepr(self):
        f = MyServerFactory()
        p = reactor.listenTCP(0, f)
        portNo = str(p.getHost().port)
        self.assertFalse(repr(p).find(portNo) == -1)

        def stoppedListening(ign):
            self.assertFalse(repr(p).find(portNo) != -1)

        d = defer.maybeDeferred(p.stopListening)
        return d.addCallback(stoppedListening)

    def test_serverRepr(self):
        """
        Check that the repr string of the server transport get the good port
        number if the server listens on 0.
        """
        server = MyServerFactory()
        serverConnMade = server.protocolConnectionMade = defer.Deferred()
        port = reactor.listenTCP(0, server)
        self.addCleanup(port.stopListening)

        client = MyClientFactory()
        clientConnMade = client.protocolConnectionMade = defer.Deferred()
        connector = reactor.connectTCP("127.0.0.1", port.getHost().port, client)
        self.addCleanup(connector.disconnect)

        def check(result):
            serverProto, clientProto = result
            portNumber = port.getHost().port
            self.assertEqual(
                repr(serverProto.transport),
                f"<AccumulatingProtocol #0 on {portNumber}>",
            )
            serverProto.transport.loseConnection()
            clientProto.transport.loseConnection()

        return defer.gatherResults([serverConnMade, clientConnMade]).addCallback(check)

    def test_restartListening(self):
        """
        Stop and then try to restart a L{tcp.Port}: after a restart, the
        server should be able to handle client connections.
        """
        serverFactory = MyServerFactory()
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        def cbStopListening(ignored):
            port.startListening()

            client = MyClientFactory()
            serverFactory.protocolConnectionMade = defer.Deferred()
            client.protocolConnectionMade = defer.Deferred()
            connector = reactor.connectTCP("127.0.0.1", port.getHost().port, client)
            self.addCleanup(connector.disconnect)
            return defer.gatherResults(
                [serverFactory.protocolConnectionMade, client.protocolConnectionMade]
            ).addCallback(close)

        def close(result):
            serverProto, clientProto = result
            clientProto.transport.loseConnection()
            serverProto.transport.loseConnection()

        d = defer.maybeDeferred(port.stopListening)
        d.addCallback(cbStopListening)
        return d

    def test_exceptInStop(self):
        """
        If the server factory raises an exception in C{stopFactory}, the
        deferred returned by L{tcp.Port.stopListening} should fail with the
        corresponding error.
        """
        serverFactory = MyServerFactory()

        def raiseException():
            raise RuntimeError("An error")

        serverFactory.stopFactory = raiseException
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")

        return self.assertFailure(port.stopListening(), RuntimeError)

    def test_restartAfterExcept(self):
        """
        Even if the server factory raise an exception in C{stopFactory}, the
        corresponding C{tcp.Port} instance should be in a sane state and can
        be restarted.
        """
        serverFactory = MyServerFactory()

        def raiseException():
            raise RuntimeError("An error")

        serverFactory.stopFactory = raiseException
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        def cbStopListening(ignored):
            del serverFactory.stopFactory
            port.startListening()

            client = MyClientFactory()
            serverFactory.protocolConnectionMade = defer.Deferred()
            client.protocolConnectionMade = defer.Deferred()
            connector = reactor.connectTCP("127.0.0.1", port.getHost().port, client)
            self.addCleanup(connector.disconnect)
            return defer.gatherResults(
                [serverFactory.protocolConnectionMade, client.protocolConnectionMade]
            ).addCallback(close)

        def close(result):
            serverProto, clientProto = result
            clientProto.transport.loseConnection()
            serverProto.transport.loseConnection()

        return self.assertFailure(port.stopListening(), RuntimeError).addCallback(
            cbStopListening
        )

    def test_directConnectionLostCall(self):
        """
        If C{connectionLost} is called directly on a port object, it succeeds
        (and doesn't expect the presence of a C{deferred} attribute).

        C{connectionLost} is called by L{reactor.disconnectAll} at shutdown.
        """
        serverFactory = MyServerFactory()
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        portNumber = port.getHost().port
        port.connectionLost(None)

        client = MyClientFactory()
        serverFactory.protocolConnectionMade = defer.Deferred()
        client.protocolConnectionMade = defer.Deferred()
        reactor.connectTCP("127.0.0.1", portNumber, client)

        def check(ign):
            client.reason.trap(error.ConnectionRefusedError)

        return client.failDeferred.addCallback(check)

    def test_exceptInConnectionLostCall(self):
        """
        If C{connectionLost} is called directory on a port object and that the
        server factory raises an exception in C{stopFactory}, the exception is
        passed through to the caller.

        C{connectionLost} is called by L{reactor.disconnectAll} at shutdown.
        """
        serverFactory = MyServerFactory()

        def raiseException():
            raise RuntimeError("An error")

        serverFactory.stopFactory = raiseException
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        self.assertRaises(RuntimeError, port.connectionLost, None)


class LoopbackTests(TestCase):
    """
    Test loopback connections.
    """

    def test_closePortInProtocolFactory(self):
        """
        A port created with L{IReactorTCP.listenTCP} can be connected to with
        L{IReactorTCP.connectTCP}.
        """
        f = ClosingFactory()
        port = reactor.listenTCP(0, f, interface="127.0.0.1")
        f.port = port
        self.addCleanup(f.cleanUp)
        portNumber = port.getHost().port
        clientF = MyClientFactory()
        reactor.connectTCP("127.0.0.1", portNumber, clientF)

        def check(x):
            self.assertTrue(clientF.protocol.made)
            self.assertTrue(port.disconnected)
            clientF.lostReason.trap(error.ConnectionDone)

        return clientF.deferred.addCallback(check)

    def _trapCnxDone(self, obj):
        getattr(obj, "trap", lambda x: None)(error.ConnectionDone)

    def _connectedClientAndServerTest(self, callback):
        """
        Invoke the given callback with a client protocol and a server protocol
        which have been connected to each other.
        """
        serverFactory = MyServerFactory()
        serverConnMade = defer.Deferred()
        serverFactory.protocolConnectionMade = serverConnMade
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        portNumber = port.getHost().port
        clientF = MyClientFactory()
        clientConnMade = defer.Deferred()
        clientF.protocolConnectionMade = clientConnMade
        reactor.connectTCP("127.0.0.1", portNumber, clientF)

        connsMade = defer.gatherResults([serverConnMade, clientConnMade])

        def connected(result):
            serverProtocol, clientProtocol = result
            callback(serverProtocol, clientProtocol)
            serverProtocol.transport.loseConnection()
            clientProtocol.transport.loseConnection()

        connsMade.addCallback(connected)
        return connsMade

    def test_tcpNoDelay(self):
        """
        The transport of a protocol connected with L{IReactorTCP.connectTCP} or
        L{IReactor.TCP.listenTCP} can have its I{TCP_NODELAY} state inspected
        and manipulated with L{ITCPTransport.getTcpNoDelay} and
        L{ITCPTransport.setTcpNoDelay}.
        """

        def check(serverProtocol, clientProtocol):
            for p in [serverProtocol, clientProtocol]:
                transport = p.transport
                self.assertEqual(transport.getTcpNoDelay(), 0)
                transport.setTcpNoDelay(1)
                self.assertEqual(transport.getTcpNoDelay(), 1)
                transport.setTcpNoDelay(0)
                self.assertEqual(transport.getTcpNoDelay(), 0)

        return self._connectedClientAndServerTest(check)

    def test_tcpKeepAlive(self):
        """
        The transport of a protocol connected with L{IReactorTCP.connectTCP} or
        L{IReactor.TCP.listenTCP} can have its I{SO_KEEPALIVE} state inspected
        and manipulated with L{ITCPTransport.getTcpKeepAlive} and
        L{ITCPTransport.setTcpKeepAlive}.
        """

        def check(serverProtocol, clientProtocol):
            for p in [serverProtocol, clientProtocol]:
                transport = p.transport
                self.assertEqual(transport.getTcpKeepAlive(), 0)
                transport.setTcpKeepAlive(1)
                self.assertEqual(transport.getTcpKeepAlive(), 1)
                transport.setTcpKeepAlive(0)
                self.assertEqual(transport.getTcpKeepAlive(), 0)

        return self._connectedClientAndServerTest(check)

    def testFailing(self):
        clientF = MyClientFactory()
        # XXX we assume no one is listening on TCP port 69
        reactor.connectTCP("127.0.0.1", 69, clientF, timeout=5)

        def check(ignored):
            clientF.reason.trap(error.ConnectionRefusedError)

        return clientF.failDeferred.addCallback(check)

    def test_connectionRefusedErrorNumber(self):
        """
        Assert that the error number of the ConnectionRefusedError is
        ECONNREFUSED, and not some other socket related error.
        """

        # Bind a number of ports in the operating system.  We will attempt
        # to connect to these in turn immediately after closing them, in the
        # hopes that no one else has bound them in the mean time.  Any
        # connection which succeeds is ignored and causes us to move on to
        # the next port.  As soon as a connection attempt fails, we move on
        # to making an assertion about how it failed.  If they all succeed,
        # the test will fail.

        # It would be nice to have a simpler, reliable way to cause a
        # connection failure from the platform.
        #
        # On Linux (2.6.15), connecting to port 0 always fails.  FreeBSD
        # (5.4) rejects the connection attempt with EADDRNOTAVAIL.
        #
        # On FreeBSD (5.4), listening on a port and then repeatedly
        # connecting to it without ever accepting any connections eventually
        # leads to an ECONNREFUSED.  On Linux (2.6.15), a seemingly
        # unbounded number of connections succeed.

        serverSockets = []
        for i in range(10):
            serverSocket = socket.socket()
            serverSocket.bind(("127.0.0.1", 0))
            serverSocket.listen(1)
            serverSockets.append(serverSocket)
        random.shuffle(serverSockets)

        clientCreator = protocol.ClientCreator(reactor, protocol.Protocol)

        def tryConnectFailure():
            def connected(proto):
                """
                Darn.  Kill it and try again, if there are any tries left.
                """
                proto.transport.loseConnection()
                if serverSockets:
                    return tryConnectFailure()
                self.fail(
                    "Could not fail to connect - could not test errno for that case."
                )

            serverSocket = serverSockets.pop()
            serverHost, serverPort = serverSocket.getsockname()
            serverSocket.close()

            connectDeferred = clientCreator.connectTCP(serverHost, serverPort)
            connectDeferred.addCallback(connected)
            return connectDeferred

        refusedDeferred = tryConnectFailure()
        self.assertFailure(refusedDeferred, error.ConnectionRefusedError)

        def connRefused(exc):
            self.assertEqual(exc.osError, errno.ECONNREFUSED)

        refusedDeferred.addCallback(connRefused)

        def cleanup(passthrough):
            while serverSockets:
                serverSockets.pop().close()
            return passthrough

        refusedDeferred.addBoth(cleanup)
        return refusedDeferred

    def test_connectByServiceFail(self):
        """
        Connecting to a named service which does not exist raises
        L{error.ServiceNameUnknownError}.
        """
        self.assertRaises(
            error.ServiceNameUnknownError,
            reactor.connectTCP,
            "127.0.0.1",
            "thisbetternotexist",
            MyClientFactory(),
        )

    def test_connectByService(self):
        """
        L{IReactorTCP.connectTCP} accepts the name of a service instead of a
        port number and connects to the port number associated with that
        service, as defined by L{socket.getservbyname}.
        """
        serverFactory = MyServerFactory()
        serverConnMade = defer.Deferred()
        serverFactory.protocolConnectionMade = serverConnMade
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)
        portNumber = port.getHost().port
        clientFactory = MyClientFactory()
        clientConnMade = defer.Deferred()
        clientFactory.protocolConnectionMade = clientConnMade

        def fakeGetServicePortByName(serviceName, protocolName):
            if serviceName == "http" and protocolName == "tcp":
                return portNumber
            return 10

        self.patch(socket, "getservbyname", fakeGetServicePortByName)

        reactor.connectTCP("127.0.0.1", "http", clientFactory)

        connMade = defer.gatherResults([serverConnMade, clientConnMade])

        def connected(result):
            serverProtocol, clientProtocol = result
            self.assertTrue(
                serverFactory.called,
                "Server factory was not called upon to build a protocol.",
            )
            serverProtocol.transport.loseConnection()
            clientProtocol.transport.loseConnection()

        connMade.addCallback(connected)
        return connMade


class StartStopFactory(protocol.Factory):

    started = 0
    stopped = 0

    def startFactory(self):
        if self.started or self.stopped:
            raise RuntimeError
        self.started = 1

    def stopFactory(self):
        if not self.started or self.stopped:
            raise RuntimeError
        self.stopped = 1


class ClientStartStopFactory(MyClientFactory):

    started = 0
    stopped = 0

    def __init__(self, *a, **kw):
        MyClientFactory.__init__(self, *a, **kw)
        self.whenStopped = defer.Deferred()

    def startFactory(self):
        if self.started or self.stopped:
            raise RuntimeError
        self.started = 1

    def stopFactory(self):
        if not self.started or self.stopped:
            raise RuntimeError
        self.stopped = 1
        self.whenStopped.callback(True)


class FactoryTests(TestCase):
    """Tests for factories."""

    def test_serverStartStop(self):
        """
        The factory passed to L{IReactorTCP.listenTCP} should be started only
        when it transitions from being used on no ports to being used on one
        port and should be stopped only when it transitions from being used on
        one port to being used on no ports.
        """
        # Note - this test doesn't need to use listenTCP.  It is exercising
        # logic implemented in Factory.doStart and Factory.doStop, so it could
        # just call that directly.  Some other test can make sure that
        # listenTCP and stopListening correctly call doStart and
        # doStop. -exarkun

        f = StartStopFactory()

        # listen on port
        p1 = reactor.listenTCP(0, f, interface="127.0.0.1")
        self.addCleanup(p1.stopListening)

        self.assertEqual((f.started, f.stopped), (1, 0))

        # listen on two more ports
        p2 = reactor.listenTCP(0, f, interface="127.0.0.1")
        p3 = reactor.listenTCP(0, f, interface="127.0.0.1")

        self.assertEqual((f.started, f.stopped), (1, 0))

        # close two ports
        d1 = defer.maybeDeferred(p1.stopListening)
        d2 = defer.maybeDeferred(p2.stopListening)
        closedDeferred = defer.gatherResults([d1, d2])

        def cbClosed(ignored):
            self.assertEqual((f.started, f.stopped), (1, 0))
            # Close the last port
            return p3.stopListening()

        closedDeferred.addCallback(cbClosed)

        def cbClosedAll(ignored):
            self.assertEqual((f.started, f.stopped), (1, 1))

        closedDeferred.addCallback(cbClosedAll)
        return closedDeferred

    def test_clientStartStop(self):
        """
        The factory passed to L{IReactorTCP.connectTCP} should be started when
        the connection attempt starts and stopped when it is over.
        """
        f = ClosingFactory()
        p = reactor.listenTCP(0, f, interface="127.0.0.1")
        f.port = p
        self.addCleanup(f.cleanUp)
        portNumber = p.getHost().port

        factory = ClientStartStopFactory()
        reactor.connectTCP("127.0.0.1", portNumber, factory)
        self.assertTrue(factory.started)
        return loopUntil(lambda: factory.stopped)


class CannotBindTests(TestCase):
    """
    Tests for correct behavior when a reactor cannot bind to the required TCP
    port.
    """

    def test_cannotBind(self):
        """
        L{IReactorTCP.listenTCP} raises L{error.CannotListenError} if the
        address to listen on is already in use.
        """
        f = MyServerFactory()

        p1 = reactor.listenTCP(0, f, interface="127.0.0.1")
        self.addCleanup(p1.stopListening)
        n = p1.getHost().port
        dest = p1.getHost()
        self.assertEqual(dest.type, "TCP")
        self.assertEqual(dest.host, "127.0.0.1")
        self.assertEqual(dest.port, n)

        # make sure new listen raises error
        self.assertRaises(
            error.CannotListenError, reactor.listenTCP, n, f, interface="127.0.0.1"
        )

    def _fireWhenDoneFunc(self, d, f):
        """Returns closure that when called calls f and then callbacks d."""

        @wraps(f)
        def newf(*args, **kw):
            rtn = f(*args, **kw)
            d.callback("")
            return rtn

        return newf

    def test_clientBind(self):
        """
        L{IReactorTCP.connectTCP} calls C{Factory.clientConnectionFailed} with
        L{error.ConnectBindError} if the bind address specified is already in
        use.
        """
        theDeferred = defer.Deferred()
        sf = MyServerFactory()
        sf.startFactory = self._fireWhenDoneFunc(theDeferred, sf.startFactory)
        p = reactor.listenTCP(0, sf, interface="127.0.0.1")
        self.addCleanup(p.stopListening)

        def _connect1(results):
            d = defer.Deferred()
            cf1 = MyClientFactory()
            cf1.buildProtocol = self._fireWhenDoneFunc(d, cf1.buildProtocol)
            reactor.connectTCP(
                "127.0.0.1", p.getHost().port, cf1, bindAddress=("127.0.0.1", 0)
            )
            d.addCallback(_conmade, cf1)
            return d

        def _conmade(results, cf1):
            d = defer.Deferred()
            cf1.protocol.connectionMade = self._fireWhenDoneFunc(
                d, cf1.protocol.connectionMade
            )
            d.addCallback(_check1connect2, cf1)
            return d

        def _check1connect2(results, cf1):
            self.assertEqual(cf1.protocol.made, 1)

            d1 = defer.Deferred()
            d2 = defer.Deferred()
            port = cf1.protocol.transport.getHost().port
            cf2 = MyClientFactory()
            cf2.clientConnectionFailed = self._fireWhenDoneFunc(
                d1, cf2.clientConnectionFailed
            )
            cf2.stopFactory = self._fireWhenDoneFunc(d2, cf2.stopFactory)
            reactor.connectTCP(
                "127.0.0.1", p.getHost().port, cf2, bindAddress=("127.0.0.1", port)
            )
            d1.addCallback(_check2failed, cf1, cf2)
            d2.addCallback(_check2stopped, cf1, cf2)
            dl = defer.DeferredList([d1, d2])
            dl.addCallback(_stop, cf1, cf2)
            return dl

        def _check2failed(results, cf1, cf2):
            self.assertEqual(cf2.failed, 1)
            cf2.reason.trap(error.ConnectBindError)
            self.assertTrue(cf2.reason.check(error.ConnectBindError))
            return results

        def _check2stopped(results, cf1, cf2):
            self.assertEqual(cf2.stopped, 1)
            return results

        def _stop(results, cf1, cf2):
            d = defer.Deferred()
            d.addCallback(_check1cleanup, cf1)
            cf1.stopFactory = self._fireWhenDoneFunc(d, cf1.stopFactory)
            cf1.protocol.transport.loseConnection()
            return d

        def _check1cleanup(results, cf1):
            self.assertEqual(cf1.stopped, 1)

        theDeferred.addCallback(_connect1)
        return theDeferred


class MyOtherClientFactory(protocol.ClientFactory):
    def buildProtocol(self, address):
        self.address = address
        self.protocol = AccumulatingProtocol()
        return self.protocol


class LocalRemoteAddressTests(TestCase):
    """
    Tests for correct getHost/getPeer values and that the correct address is
    passed to buildProtocol.
    """

    def test_hostAddress(self):
        """
        L{IListeningPort.getHost} returns the same address as a client
        connection's L{ITCPTransport.getPeer}.
        """
        serverFactory = MyServerFactory()
        serverFactory.protocolConnectionLost = defer.Deferred()
        serverConnectionLost = serverFactory.protocolConnectionLost
        port = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        self.addCleanup(port.stopListening)
        n = port.getHost().port

        clientFactory = MyClientFactory()
        onConnection = clientFactory.protocolConnectionMade = defer.Deferred()
        connector = reactor.connectTCP("127.0.0.1", n, clientFactory)

        def check(ignored):
            self.assertEqual([port.getHost()], clientFactory.peerAddresses)
            self.assertEqual(port.getHost(), clientFactory.protocol.transport.getPeer())

        onConnection.addCallback(check)

        def cleanup(ignored):
            # Clean up the client explicitly here so that tear down of
            # the server side of the connection begins, then wait for
            # the server side to actually disconnect.
            connector.disconnect()
            return serverConnectionLost

        onConnection.addCallback(cleanup)

        return onConnection


class WriterProtocol(protocol.Protocol):
    def connectionMade(self):
        # use everything ITransport claims to provide. If something here
        # fails, the exception will be written to the log, but it will not
        # directly flunk the test. The test will fail when maximum number of
        # iterations have passed and the writer's factory.done has not yet
        # been set.
        self.transport.write(b"Hello Cleveland!\n")
        seq = [b"Goodbye", b" cruel", b" world", b"\n"]
        self.transport.writeSequence(seq)
        peer = self.transport.getPeer()
        if peer.type != "TCP":
            msg(f"getPeer returned non-TCP socket: {peer}")
            self.factory.problem = 1
        us = self.transport.getHost()
        if us.type != "TCP":
            msg(f"getHost returned non-TCP socket: {us}")
            self.factory.problem = 1
        self.factory.done = 1

        self.transport.loseConnection()


class ReaderProtocol(protocol.Protocol):
    def dataReceived(self, data):
        self.factory.data += data

    def connectionLost(self, reason):
        self.factory.done = 1


class WriterClientFactory(protocol.ClientFactory):
    def __init__(self):
        self.done = 0
        self.data = b""

    def buildProtocol(self, addr):
        p = ReaderProtocol()
        p.factory = self
        self.protocol = p
        return p


class WriteDataTests(TestCase):
    """
    Test that connected TCP sockets can actually write data. Try to exercise
    the entire ITransport interface.
    """

    def test_writer(self):
        """
        L{ITCPTransport.write} and L{ITCPTransport.writeSequence} send bytes to
        the other end of the connection.
        """
        f = protocol.Factory()
        f.protocol = WriterProtocol
        f.done = 0
        f.problem = 0
        wrappedF = WiredFactory(f)
        p = reactor.listenTCP(0, wrappedF, interface="127.0.0.1")
        self.addCleanup(p.stopListening)
        n = p.getHost().port
        clientF = WriterClientFactory()
        wrappedClientF = WiredFactory(clientF)
        reactor.connectTCP("127.0.0.1", n, wrappedClientF)

        def check(ignored):
            self.assertTrue(f.done, "writer didn't finish, it probably died")
            self.assertTrue(f.problem == 0, "writer indicated an error")
            self.assertTrue(clientF.done, "client didn't see connection dropped")
            expected = b"".join(
                [b"Hello Cleveland!\n", b"Goodbye", b" cruel", b" world", b"\n"]
            )
            self.assertTrue(
                clientF.data == expected,
                "client didn't receive all the data it expected",
            )

        d = defer.gatherResults([wrappedF.onDisconnect, wrappedClientF.onDisconnect])
        return d.addCallback(check)

    def test_writeAfterShutdownWithoutReading(self):
        """
        A TCP transport which is written to after the connection has been shut
        down should notify its protocol that the connection has been lost, even
        if the TCP transport is not actively being monitored for read events
        (ie, pauseProducing was called on it).
        """
        # This is an unpleasant thing.  Generally tests shouldn't skip or
        # run based on the name of the reactor being used (most tests
        # shouldn't care _at all_ what reactor is being used, in fact).  The
        # IOCP reactor cannot pass this test, though -- please see the skip
        # reason below for details.
        if reactor.__class__.__name__ == "IOCPReactor":
            raise SkipTest(
                "iocpreactor does not, in fact, stop reading immediately "
                "after pauseProducing is called. This results in a "
                "bonus disconnection notification. Under some "
                "circumstances, it might be possible to not receive "
                "this notifications (specifically, pauseProducing, "
                "deliver some data, proceed with this test). "
            )

        # Called back after the protocol for the client side of the connection
        # has paused its transport, preventing it from reading, therefore
        # preventing it from noticing the disconnection before the rest of the
        # actions which are necessary to trigger the case this test is for have
        # been taken.
        clientPaused = defer.Deferred()

        # Called back when the protocol for the server side of the connection
        # has received connection lost notification.
        serverLost = defer.Deferred()

        class Disconnecter(protocol.Protocol):
            """
            Protocol for the server side of the connection which disconnects
            itself in a callback on clientPaused and publishes notification
            when its connection is actually lost.
            """

            def connectionMade(self):
                """
                Set up a callback on clientPaused to lose the connection.
                """
                msg("Disconnector.connectionMade")

                def disconnect(ignored):
                    msg("Disconnector.connectionMade disconnect")
                    self.transport.loseConnection()
                    msg("loseConnection called")

                clientPaused.addCallback(disconnect)

            def connectionLost(self, reason):
                """
                Notify observers that the server side of the connection has
                ended.
                """
                msg("Disconnecter.connectionLost")
                serverLost.callback(None)
                msg("serverLost called back")

        # Create the server port to which a connection will be made.
        server = protocol.ServerFactory()
        server.protocol = Disconnecter
        port = reactor.listenTCP(0, server, interface="127.0.0.1")
        self.addCleanup(port.stopListening)
        addr = port.getHost()

        @implementer(IPullProducer)
        class Infinite:
            """
            A producer which will write to its consumer as long as
            resumeProducing is called.

            @ivar consumer: The L{IConsumer} which will be written to.
            """

            def __init__(self, consumer):
                self.consumer = consumer

            def resumeProducing(self):
                msg("Infinite.resumeProducing")
                self.consumer.write(b"x")
                msg("Infinite.resumeProducing wrote to consumer")

            def stopProducing(self):
                msg("Infinite.stopProducing")

        class UnreadingWriter(protocol.Protocol):
            """
            Trivial protocol which pauses its transport immediately and then
            writes some bytes to it.
            """

            def connectionMade(self):
                msg("UnreadingWriter.connectionMade")
                self.transport.pauseProducing()
                clientPaused.callback(None)
                msg("clientPaused called back")

                def write(ignored):
                    msg("UnreadingWriter.connectionMade write")
                    # This needs to be enough bytes to spill over into the
                    # userspace Twisted send buffer - if it all fits into
                    # the kernel, Twisted won't even poll for OUT events,
                    # which means it won't poll for any events at all, so
                    # the disconnection is never noticed.  This is due to
                    # #1662.  When #1662 is fixed, this test will likely
                    # need to be adjusted, otherwise connection lost
                    # notification will happen too soon and the test will
                    # probably begin to fail with ConnectionDone instead of
                    # ConnectionLost (in any case, it will no longer be
                    # entirely correct).
                    producer = Infinite(self.transport)
                    msg("UnreadingWriter.connectionMade write created producer")
                    self.transport.registerProducer(producer, False)
                    msg("UnreadingWriter.connectionMade write registered producer")

                serverLost.addCallback(write)

        # Create the client and initiate the connection
        client = MyClientFactory()
        client.protocolFactory = UnreadingWriter
        clientConnectionLost = client.deferred

        def cbClientLost(ignored):
            msg("cbClientLost")
            return client.lostReason

        clientConnectionLost.addCallback(cbClientLost)
        msg(f"Connecting to {addr.host}:{addr.port}")
        reactor.connectTCP(addr.host, addr.port, client)

        # By the end of the test, the client should have received notification
        # of unclean disconnection.
        msg("Returning Deferred")
        return self.assertFailure(clientConnectionLost, error.ConnectionLost)


class ConnectionLosingProtocol(protocol.Protocol):
    def connectionMade(self):
        self.transport.write(b"1")
        self.transport.loseConnection()
        self.master._connectionMade()
        self.master.ports.append(self.transport)


class NoopProtocol(protocol.Protocol):
    def connectionMade(self):
        self.d = defer.Deferred()
        self.master.serverConns.append(self.d)

    def connectionLost(self, reason):
        self.d.callback(True)


class ConnectionLostNotifyingProtocol(protocol.Protocol):
    """
    Protocol which fires a Deferred which was previously passed to
    its initializer when the connection is lost.

    @ivar onConnectionLost: The L{Deferred} which will be fired in
        C{connectionLost}.

    @ivar lostConnectionReason: L{None} until the connection is lost, then a
        reference to the reason passed to C{connectionLost}.
    """

    def __init__(self, onConnectionLost):
        self.lostConnectionReason = None
        self.onConnectionLost = onConnectionLost

    def connectionLost(self, reason):
        self.lostConnectionReason = reason
        self.onConnectionLost.callback(self)


class HandleSavingProtocol(ConnectionLostNotifyingProtocol):
    """
    Protocol which grabs the platform-specific socket handle and
    saves it as an attribute on itself when the connection is
    established.
    """

    def makeConnection(self, transport):
        """
        Save the platform-specific socket handle for future
        introspection.
        """
        self.handle = transport.getHandle()
        return protocol.Protocol.makeConnection(self, transport)


class ProperlyCloseFilesMixin:
    """
    Tests for platform resources properly being cleaned up.
    """

    def createServer(self, address, portNumber, factory):
        """
        Bind a server port to which connections will be made.  The server
        should use the given protocol factory.

        @return: The L{IListeningPort} for the server created.
        """
        raise NotImplementedError()

    def connectClient(self, address, portNumber, clientCreator):
        """
        Establish a connection to the given address using the given
        L{ClientCreator} instance.

        @return: A Deferred which will fire with the connected protocol instance.
        """
        raise NotImplementedError()

    def getHandleExceptionType(self):
        """
        Return the exception class which will be raised when an operation is
        attempted on a closed platform handle.
        """
        raise NotImplementedError()

    def getHandleErrorCodeMatcher(self):
        """
        Return a L{hamcrest.core.matcher.Matcher} that matches the
        errno expected to result from writing to a closed platform
        socket handle.
        """
        # Windows: returns WSAENOTSOCK
        # Linux, FreeBSD, macOS: returns EBADF
        if platform.isWindows():
            return hamcrest.equal_to(errno.WSAENOTSOCK)
        return hamcrest.equal_to(errno.EBADF)

    def test_properlyCloseFiles(self):
        """
        Test that lost connections properly have their underlying socket
        resources cleaned up.
        """
        onServerConnectionLost = defer.Deferred()
        serverFactory = protocol.ServerFactory()
        serverFactory.protocol = lambda: ConnectionLostNotifyingProtocol(
            onServerConnectionLost
        )
        serverPort = self.createServer("127.0.0.1", 0, serverFactory)

        onClientConnectionLost = defer.Deferred()
        serverAddr = serverPort.getHost()
        clientCreator = protocol.ClientCreator(
            reactor, lambda: HandleSavingProtocol(onClientConnectionLost)
        )
        clientDeferred = self.connectClient(
            serverAddr.host, serverAddr.port, clientCreator
        )

        def clientConnected(client):
            """
            Disconnect the client.  Return a Deferred which fires when both
            the client and the server have received disconnect notification.
            """
            client.transport.write(b"some bytes to make sure the connection is set up")
            client.transport.loseConnection()
            return defer.gatherResults([onClientConnectionLost, onServerConnectionLost])

        clientDeferred.addCallback(clientConnected)

        def clientDisconnected(result):
            """
            Verify that the underlying platform socket handle has been
            cleaned up.
            """
            client, server = result
            if not client.lostConnectionReason.check(error.ConnectionClosed):
                err(
                    client.lostConnectionReason,
                    "Client lost connection for unexpected reason",
                )
            if not server.lostConnectionReason.check(error.ConnectionClosed):
                err(
                    server.lostConnectionReason,
                    "Server lost connection for unexpected reason",
                )
            errorCodeMatcher = self.getHandleErrorCodeMatcher()
            exception = self.assertRaises(
                self.getHandleExceptionType(), client.handle.send, b"bytes"
            )
            hamcrest.assert_that(
                exception.args[0],
                errorCodeMatcher,
            )

        clientDeferred.addCallback(clientDisconnected)

        def cleanup(passthrough):
            """
            Shut down the server port.  Return a Deferred which fires when
            this has completed.
            """
            result = defer.maybeDeferred(serverPort.stopListening)
            result.addCallback(lambda ign: passthrough)
            return result

        clientDeferred.addBoth(cleanup)

        return clientDeferred


class ProperlyCloseFilesTests(TestCase, ProperlyCloseFilesMixin):
    """
    Test that the sockets created by L{IReactorTCP.connectTCP} are cleaned up
    when the connection they are associated with is closed.
    """

    def createServer(self, address, portNumber, factory):
        """
        Create a TCP server using L{IReactorTCP.listenTCP}.
        """
        return reactor.listenTCP(portNumber, factory, interface=address)

    def connectClient(self, address, portNumber, clientCreator):
        """
        Create a TCP client using L{IReactorTCP.connectTCP}.
        """
        return clientCreator.connectTCP(address, portNumber)

    def getHandleExceptionType(self):
        """
        Return L{socket.error} as the expected error type which will be
        raised by a write to the low-level socket object after it has been
        closed.
        """
        return socket.error


class WiredForDeferreds(policies.ProtocolWrapper):
    def __init__(self, factory, wrappedProtocol):
        policies.ProtocolWrapper.__init__(self, factory, wrappedProtocol)

    def connectionMade(self):
        policies.ProtocolWrapper.connectionMade(self)
        self.factory.onConnect.callback(None)

    def connectionLost(self, reason):
        policies.ProtocolWrapper.connectionLost(self, reason)
        self.factory.onDisconnect.callback(None)


class WiredFactory(policies.WrappingFactory):
    protocol = WiredForDeferreds

    def __init__(self, wrappedFactory):
        policies.WrappingFactory.__init__(self, wrappedFactory)
        self.onConnect = defer.Deferred()
        self.onDisconnect = defer.Deferred()


class AddressTests(TestCase):
    """
    Tests for address-related interactions with client and server protocols.
    """

    def setUp(self):
        """
        Create a port and connected client/server pair which can be used
        to test factory behavior related to addresses.

        @return: A L{defer.Deferred} which will be called back when both the
            client and server protocols have received their connection made
            callback.
        """

        class RememberingWrapper(protocol.ClientFactory):
            """
            Simple wrapper factory which records the addresses which are
            passed to its L{buildProtocol} method and delegates actual
            protocol creation to another factory.

            @ivar addresses: A list of the objects passed to buildProtocol.
            @ivar factory: The wrapped factory to which protocol creation is
                delegated.
            """

            def __init__(self, factory):
                self.addresses = []
                self.factory = factory

            # Only bother to pass on buildProtocol calls to the wrapped
            # factory - doStart, doStop, etc aren't necessary for this test
            # to pass.
            def buildProtocol(self, addr):
                """
                Append the given address to C{self.addresses} and forward
                the call to C{self.factory}.
                """
                self.addresses.append(addr)
                return self.factory.buildProtocol(addr)

        # Make a server which we can receive connection and disconnection
        # notification for, and which will record the address passed to its
        # buildProtocol.
        self.server = MyServerFactory()
        self.serverConnMade = self.server.protocolConnectionMade = defer.Deferred()
        self.serverConnLost = self.server.protocolConnectionLost = defer.Deferred()
        # RememberingWrapper is a ClientFactory, but ClientFactory is-a
        # ServerFactory, so this is okay.
        self.serverWrapper = RememberingWrapper(self.server)

        # Do something similar for a client.
        self.client = MyClientFactory()
        self.clientConnMade = self.client.protocolConnectionMade = defer.Deferred()
        self.clientConnLost = self.client.protocolConnectionLost = defer.Deferred()
        self.clientWrapper = RememberingWrapper(self.client)

        self.port = reactor.listenTCP(0, self.serverWrapper, interface="127.0.0.1")
        self.connector = reactor.connectTCP(
            self.port.getHost().host, self.port.getHost().port, self.clientWrapper
        )

        return defer.gatherResults([self.serverConnMade, self.clientConnMade])

    def tearDown(self):
        """
        Disconnect the client/server pair and shutdown the port created in
        L{setUp}.
        """
        self.connector.disconnect()
        return defer.gatherResults(
            [
                self.serverConnLost,
                self.clientConnLost,
                defer.maybeDeferred(self.port.stopListening),
            ]
        )

    def test_buildProtocolClient(self):
        """
        L{ClientFactory.buildProtocol} should be invoked with the address of
        the server to which a connection has been established, which should
        be the same as the address reported by the C{getHost} method of the
        transport of the server protocol and as the C{getPeer} method of the
        transport of the client protocol.
        """
        serverHost = self.server.protocol.transport.getHost()
        clientPeer = self.client.protocol.transport.getPeer()

        self.assertEqual(
            self.clientWrapper.addresses,
            [IPv4Address("TCP", serverHost.host, serverHost.port)],
        )
        self.assertEqual(
            self.clientWrapper.addresses,
            [IPv4Address("TCP", clientPeer.host, clientPeer.port)],
        )


class LargeBufferWriterProtocol(protocol.Protocol):
    # Win32 sockets cannot handle single huge chunks of bytes.  Write one
    # massive string to make sure Twisted deals with this fact. Immediately
    # follow that with another write to test behaviour under load (see issue
    # #9446)

    def connectionMade(self):
        self.transport.write(b"X" * (self.factory.len - 1))

        def finish():
            self.transport.write(b"X")
            self.factory.done = 1
            self.transport.loseConnection()

        reactor.callLater(0.001, finish)


class LargeBufferReaderProtocol(protocol.Protocol):
    def dataReceived(self, data):
        self.factory.len += len(data)

    def connectionLost(self, reason):
        self.factory.done = 1


class LargeBufferReaderClientFactory(protocol.ClientFactory):
    def __init__(self):
        self.done = 0
        self.len = 0

    def buildProtocol(self, addr):
        p = LargeBufferReaderProtocol()
        p.factory = self
        self.protocol = p
        return p


class FireOnClose(policies.ProtocolWrapper):
    """A wrapper around a protocol that makes it fire a deferred when
    connectionLost is called.
    """

    def connectionLost(self, reason):
        policies.ProtocolWrapper.connectionLost(self, reason)
        self.factory.deferred.callback(None)


class FireOnCloseFactory(policies.WrappingFactory):
    protocol = FireOnClose

    def __init__(self, wrappedFactory):
        policies.WrappingFactory.__init__(self, wrappedFactory)
        self.deferred = defer.Deferred()


class LargeBufferTests(TestCase):
    """Test that buffering large amounts of data works."""

    datalen = 60 * 1024 * 1024

    def testWriter(self):
        f = protocol.Factory()
        f.protocol = LargeBufferWriterProtocol
        f.done = 0
        f.problem = 0
        f.len = self.datalen
        wrappedF = FireOnCloseFactory(f)
        p = reactor.listenTCP(0, wrappedF, interface="127.0.0.1")
        self.addCleanup(p.stopListening)
        n = p.getHost().port
        clientF = LargeBufferReaderClientFactory()
        wrappedClientF = FireOnCloseFactory(clientF)
        reactor.connectTCP("127.0.0.1", n, wrappedClientF)

        d = defer.gatherResults([wrappedF.deferred, wrappedClientF.deferred])

        def check(ignored):
            self.assertTrue(f.done, "writer didn't finish, it probably died")
            self.assertTrue(
                clientF.len >= self.datalen,
                "client didn't receive all the data it expected "
                "(%d != %d)" % (clientF.len, self.datalen),
            )
            self.assertTrue(
                clientF.len <= self.datalen,
                "client did receive more data than it expected "
                "(%d != %d)" % (clientF.len, self.datalen),
            )
            self.assertTrue(clientF.done, "client didn't see connection dropped")

        return d.addCallback(check)


@implementer(IHalfCloseableProtocol)
class MyHCProtocol(AccumulatingProtocol):

    readHalfClosed = False
    writeHalfClosed = False

    def readConnectionLost(self):
        self.readHalfClosed = True
        # Invoke notification logic from the base class to simplify testing.
        if self.writeHalfClosed:
            self.connectionLost(None)

    def writeConnectionLost(self):
        self.writeHalfClosed = True
        # Invoke notification logic from the base class to simplify testing.
        if self.readHalfClosed:
            self.connectionLost(None)


class MyHCFactory(protocol.ServerFactory):

    called = 0
    protocolConnectionMade = None

    def buildProtocol(self, addr):
        self.called += 1
        p = MyHCProtocol()
        p.factory = self
        self.protocol = p
        return p


class HalfCloseTests(TestCase):
    """Test half-closing connections."""

    def setUp(self):
        self.f = f = MyHCFactory()
        self.p = p = reactor.listenTCP(0, f, interface="127.0.0.1")
        self.addCleanup(p.stopListening)
        d = loopUntil(lambda: p.connected)

        self.cf = protocol.ClientCreator(reactor, MyHCProtocol)

        d.addCallback(lambda _: self.cf.connectTCP(p.getHost().host, p.getHost().port))
        d.addCallback(self._setUp)
        return d

    def _setUp(self, client):
        self.client = client
        self.clientProtoConnectionLost = self.client.closedDeferred = defer.Deferred()
        self.assertEqual(self.client.transport.connected, 1)
        # Wait for the server to notice there is a connection, too.
        return loopUntil(lambda: getattr(self.f, "protocol", None) is not None)

    def tearDown(self):
        self.assertEqual(self.client.closed, 0)
        self.client.transport.loseConnection()
        d = defer.maybeDeferred(self.p.stopListening)
        d.addCallback(lambda ign: self.clientProtoConnectionLost)
        d.addCallback(self._tearDown)
        return d

    def _tearDown(self, ignored):
        self.assertEqual(self.client.closed, 1)
        # because we did half-close, the server also needs to
        # closed explicitly.
        self.assertEqual(self.f.protocol.closed, 0)
        d = defer.Deferred()

        def _connectionLost(reason):
            self.f.protocol.closed = 1
            d.callback(None)

        self.f.protocol.connectionLost = _connectionLost
        self.f.protocol.transport.loseConnection()
        d.addCallback(lambda x: self.assertEqual(self.f.protocol.closed, 1))
        return d

    def testCloseWriteCloser(self):
        client = self.client
        f = self.f
        t = client.transport

        t.write(b"hello")
        d = loopUntil(lambda: len(t._tempDataBuffer) == 0)

        def loseWrite(ignored):
            t.loseWriteConnection()
            return loopUntil(lambda: t._writeDisconnected)

        def check(ignored):
            self.assertFalse(client.closed)
            self.assertTrue(client.writeHalfClosed)
            self.assertFalse(client.readHalfClosed)
            return loopUntil(lambda: f.protocol.readHalfClosed)

        def write(ignored):
            w = client.transport.write
            w(b" world")
            w(b"lalala fooled you")
            self.assertEqual(0, len(client.transport._tempDataBuffer))
            self.assertEqual(f.protocol.data, b"hello")
            self.assertFalse(f.protocol.closed)
            self.assertTrue(f.protocol.readHalfClosed)

        return d.addCallback(loseWrite).addCallback(check).addCallback(write)

    def testWriteCloseNotification(self):
        f = self.f
        f.protocol.transport.loseWriteConnection()

        d = defer.gatherResults(
            [
                loopUntil(lambda: f.protocol.writeHalfClosed),
                loopUntil(lambda: self.client.readHalfClosed),
            ]
        )
        d.addCallback(lambda _: self.assertEqual(f.protocol.readHalfClosed, False))
        return d


class HalfCloseNoNotificationAndShutdownExceptionTests(TestCase):
    def setUp(self):
        self.f = f = MyServerFactory()
        self.f.protocolConnectionMade = defer.Deferred()
        self.p = p = reactor.listenTCP(0, f, interface="127.0.0.1")

        # XXX we don't test server side yet since we don't do it yet
        d = protocol.ClientCreator(reactor, AccumulatingProtocol).connectTCP(
            p.getHost().host, p.getHost().port
        )
        d.addCallback(self._gotClient)
        return d

    def _gotClient(self, client):
        self.client = client
        # Now wait for the server to catch up - it doesn't matter if this
        # Deferred has already fired and gone away, in that case we'll
        # return None and not wait at all, which is precisely correct.
        return self.f.protocolConnectionMade

    def tearDown(self):
        self.client.transport.loseConnection()
        return self.p.stopListening()

    def testNoNotification(self):
        """
        TCP protocols support half-close connections, but not all of them
        support being notified of write closes.  In this case, test that
        half-closing the connection causes the peer's connection to be
        closed.
        """
        self.client.transport.write(b"hello")
        self.client.transport.loseWriteConnection()
        self.f.protocol.closedDeferred = d = defer.Deferred()
        self.client.closedDeferred = d2 = defer.Deferred()
        d.addCallback(lambda x: self.assertEqual(self.f.protocol.data, b"hello"))
        d.addCallback(lambda x: self.assertTrue(self.f.protocol.closed))
        return defer.gatherResults([d, d2])

    def testShutdownException(self):
        """
        If the other side has already closed its connection,
        loseWriteConnection should pass silently.
        """
        self.f.protocol.transport.loseConnection()
        self.client.transport.write(b"X")
        self.client.transport.loseWriteConnection()
        self.f.protocol.closedDeferred = d = defer.Deferred()
        self.client.closedDeferred = d2 = defer.Deferred()
        d.addCallback(lambda x: self.assertTrue(self.f.protocol.closed))
        return defer.gatherResults([d, d2])


class HalfCloseBuggyApplicationTests(TestCase):
    """
    Test half-closing connections where notification code has bugs.
    """

    def setUp(self):
        """
        Set up a server and connect a client to it.  Return a Deferred which
        only fires once this is done.
        """
        self.serverFactory = MyHCFactory()
        self.serverFactory.protocolConnectionMade = defer.Deferred()
        self.port = reactor.listenTCP(0, self.serverFactory, interface="127.0.0.1")
        self.addCleanup(self.port.stopListening)
        addr = self.port.getHost()
        creator = protocol.ClientCreator(reactor, MyHCProtocol)
        clientDeferred = creator.connectTCP(addr.host, addr.port)

        def setClient(clientProtocol):
            self.clientProtocol = clientProtocol

        clientDeferred.addCallback(setClient)
        return defer.gatherResults(
            [self.serverFactory.protocolConnectionMade, clientDeferred]
        )

    def aBug(self, *args):
        """
        Fake implementation of a callback which illegally raises an
        exception.
        """
        raise RuntimeError("ONO I AM BUGGY CODE")

    def _notificationRaisesTest(self):
        """
        Helper for testing that an exception is logged by the time the
        client protocol loses its connection.
        """
        closed = self.clientProtocol.closedDeferred = defer.Deferred()
        self.clientProtocol.transport.loseWriteConnection()

        def check(ignored):
            errors = self.flushLoggedErrors(RuntimeError)
            self.assertEqual(len(errors), 1)

        closed.addCallback(check)
        return closed

    def test_readNotificationRaises(self):
        """
        If C{readConnectionLost} raises an exception when the transport
        calls it to notify the protocol of that event, the exception should
        be logged and the protocol should be disconnected completely.
        """
        self.serverFactory.protocol.readConnectionLost = self.aBug
        return self._notificationRaisesTest()

    def test_writeNotificationRaises(self):
        """
        If C{writeConnectionLost} raises an exception when the transport
        calls it to notify the protocol of that event, the exception should
        be logged and the protocol should be disconnected completely.
        """
        self.clientProtocol.writeConnectionLost = self.aBug
        return self._notificationRaisesTest()


class LogTests(TestCase):
    """
    Test logging facility of TCP base classes.
    """

    def test_logstrClientSetup(self):
        """
        Check that the log customization of the client transport happens
        once the client is connected.
        """
        server = MyServerFactory()

        client = MyClientFactory()
        client.protocolConnectionMade = defer.Deferred()

        port = reactor.listenTCP(0, server, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        connector = reactor.connectTCP(port.getHost().host, port.getHost().port, client)
        self.addCleanup(connector.disconnect)

        # It should still have the default value
        self.assertEqual(connector.transport.logstr, "Uninitialized")

        def cb(ign):
            self.assertEqual(connector.transport.logstr, "AccumulatingProtocol,client")

        client.protocolConnectionMade.addCallback(cb)
        return client.protocolConnectionMade


class PauseProducingTests(TestCase):
    """
    Test some behaviors of pausing the production of a transport.
    """

    @skipIf(
        not interfaces.IReactorFDSet.providedBy(reactor),
        "Reactor not providing IReactorFDSet",
    )
    def test_pauseProducingInConnectionMade(self):
        """
        In C{connectionMade} of a client protocol, C{pauseProducing} used to be
        ignored: this test is here to ensure it's not ignored.
        """
        server = MyServerFactory()

        client = MyClientFactory()
        client.protocolConnectionMade = defer.Deferred()

        port = reactor.listenTCP(0, server, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        connector = reactor.connectTCP(port.getHost().host, port.getHost().port, client)
        self.addCleanup(connector.disconnect)

        def checkInConnectionMade(proto):
            tr = proto.transport
            # The transport should already be monitored
            self.assertIn(tr, reactor.getReaders() + reactor.getWriters())
            proto.transport.pauseProducing()
            self.assertNotIn(tr, reactor.getReaders() + reactor.getWriters())
            d = defer.Deferred()
            d.addCallback(checkAfterConnectionMade)
            reactor.callLater(0, d.callback, proto)
            return d

        def checkAfterConnectionMade(proto):
            tr = proto.transport
            # The transport should still not be monitored
            self.assertNotIn(tr, reactor.getReaders() + reactor.getWriters())

        client.protocolConnectionMade.addCallback(checkInConnectionMade)
        return client.protocolConnectionMade


class CallBackOrderTests(TestCase):
    """
    Test the order of reactor callbacks
    """

    def test_loseOrder(self):
        """
        Check that Protocol.connectionLost is called before factory's
        clientConnectionLost
        """
        server = MyServerFactory()
        server.protocolConnectionMade = defer.Deferred().addCallback(
            lambda proto: self.addCleanup(proto.transport.loseConnection)
        )

        client = MyClientFactory()
        client.protocolConnectionLost = defer.Deferred()
        client.protocolConnectionMade = defer.Deferred()

        def _cbCM(res):
            """
            protocol.connectionMade callback
            """
            reactor.callLater(0, client.protocol.transport.loseConnection)

        client.protocolConnectionMade.addCallback(_cbCM)

        port = reactor.listenTCP(0, server, interface="127.0.0.1")
        self.addCleanup(port.stopListening)

        connector = reactor.connectTCP(port.getHost().host, port.getHost().port, client)
        self.addCleanup(connector.disconnect)

        def _cbCCL(res):
            """
            factory.clientConnectionLost callback
            """
            return "CCL"

        def _cbCL(res):
            """
            protocol.connectionLost callback
            """
            return "CL"

        def _cbGather(res):
            self.assertEqual(res, ["CL", "CCL"])

        d = defer.gatherResults(
            [
                client.protocolConnectionLost.addCallback(_cbCL),
                client.deferred.addCallback(_cbCCL),
            ]
        )
        return d.addCallback(_cbGather)


try:
    import resource
except ImportError:
    pass
else:
    numRounds = resource.getrlimit(resource.RLIMIT_NOFILE)[0] + 10
    setattr(ProperlyCloseFilesTests, "numberRounds", numRounds)
