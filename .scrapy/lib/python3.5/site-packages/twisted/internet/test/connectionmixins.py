# -*- test-case-name: twisted.internet.test.test_tcp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Various helpers for tests for connection-oriented transports.
"""

from __future__ import division, absolute_import

import socket

from gc import collect
from weakref import ref

from zope.interface.verify import verifyObject

from twisted.python import context, log
from twisted.python.failure import Failure
from twisted.python.runtime import platform
from twisted.python.log import ILogContext, msg, err
from twisted.internet.defer import Deferred, gatherResults
from twisted.internet.interfaces import IConnector, IReactorFDSet
from twisted.internet.protocol import ClientFactory, Protocol, ServerFactory
from twisted.trial.unittest import SkipTest
from twisted.internet.test.reactormixins import needsRunningReactor
from twisted.test.test_tcp import ClosingProtocol



def findFreePort(interface='127.0.0.1', family=socket.AF_INET,
                 type=socket.SOCK_STREAM):
    """
    Ask the platform to allocate a free port on the specified interface, then
    release the socket and return the address which was allocated.

    @param interface: The local address to try to bind the port on.
    @type interface: C{str}

    @param type: The socket type which will use the resulting port.

    @return: A two-tuple of address and port, like that returned by
        L{socket.getsockname}.
    """
    addr = socket.getaddrinfo(interface, 0)[0][4]
    probe = socket.socket(family, type)
    try:
        probe.bind(addr)
        return probe.getsockname()
    finally:
        probe.close()



class ConnectableProtocol(Protocol):
    """
    A protocol to be used with L{runProtocolsWithReactor}.

    The protocol and its pair should eventually disconnect from each other.

    @ivar reactor: The reactor used in this test.

    @ivar disconnectReason: The L{Failure} passed to C{connectionLost}.

    @ivar _done: A L{Deferred} which will be fired when the connection is
        lost.
    """

    disconnectReason = None

    def _setAttributes(self, reactor, done):
        """
        Set attributes on the protocol that are known only externally; this
        will be called by L{runProtocolsWithReactor} when this protocol is
        instantiated.

        @param reactor: The reactor used in this test.

        @param done: A L{Deferred} which will be fired when the connection is
           lost.
        """
        self.reactor = reactor
        self._done = done


    def connectionLost(self, reason):
        self.disconnectReason = reason
        self._done.callback(None)
        del self._done



class EndpointCreator:
    """
    Create client and server endpoints that know how to connect to each other.
    """

    def server(self, reactor):
        """
        Return an object providing C{IStreamServerEndpoint} for use in creating
        a server to use to establish the connection type to be tested.
        """
        raise NotImplementedError()


    def client(self, reactor, serverAddress):
        """
        Return an object providing C{IStreamClientEndpoint} for use in creating
        a client to use to establish the connection type to be tested.
        """
        raise NotImplementedError()



class _SingleProtocolFactory(ClientFactory):
    """
    Factory to be used by L{runProtocolsWithReactor}.

    It always returns the same protocol (i.e. is intended for only a single
    connection).
    """

    def __init__(self, protocol):
        self._protocol = protocol


    def buildProtocol(self, addr):
        return self._protocol



def runProtocolsWithReactor(reactorBuilder, serverProtocol, clientProtocol,
                            endpointCreator):
    """
    Connect two protocols using endpoints and a new reactor instance.

    A new reactor will be created and run, with the client and server protocol
    instances connected to each other using the given endpoint creator. The
    protocols should run through some set of tests, then disconnect; when both
    have disconnected the reactor will be stopped and the function will
    return.

    @param reactorBuilder: A L{ReactorBuilder} instance.

    @param serverProtocol: A L{ConnectableProtocol} that will be the server.

    @param clientProtocol: A L{ConnectableProtocol} that will be the client.

    @param endpointCreator: An instance of L{EndpointCreator}.

    @return: The reactor run by this test.
    """
    reactor = reactorBuilder.buildReactor()
    serverProtocol._setAttributes(reactor, Deferred())
    clientProtocol._setAttributes(reactor, Deferred())
    serverFactory = _SingleProtocolFactory(serverProtocol)
    clientFactory = _SingleProtocolFactory(clientProtocol)

    # Listen on a port:
    serverEndpoint = endpointCreator.server(reactor)
    d = serverEndpoint.listen(serverFactory)

    # Connect to the port:
    def gotPort(p):
        clientEndpoint = endpointCreator.client(
            reactor, p.getHost())
        return clientEndpoint.connect(clientFactory)
    d.addCallback(gotPort)

    # Stop reactor when both connections are lost:
    def failed(result):
        log.err(result, "Connection setup failed.")
    disconnected = gatherResults([serverProtocol._done, clientProtocol._done])
    d.addCallback(lambda _: disconnected)
    d.addErrback(failed)
    d.addCallback(lambda _: needsRunningReactor(reactor, reactor.stop))

    reactorBuilder.runReactor(reactor)
    return reactor



def _getWriters(reactor):
    """
    Like L{IReactorFDSet.getWriters}, but with support for IOCP reactor as
    well.
    """
    if IReactorFDSet.providedBy(reactor):
        return reactor.getWriters()
    elif 'IOCP' in reactor.__class__.__name__:
        return reactor.handles
    else:
        # Cannot tell what is going on.
        raise Exception("Cannot find writers on %r" % (reactor,))



class _AcceptOneClient(ServerFactory):
    """
    This factory fires a L{Deferred} with a protocol instance shortly after it
    is constructed (hopefully long enough afterwards so that it has been
    connected to a transport).

    @ivar reactor: The reactor used to schedule the I{shortly}.

    @ivar result: A L{Deferred} which will be fired with the protocol instance.
    """
    def __init__(self, reactor, result):
        self.reactor = reactor
        self.result = result


    def buildProtocol(self, addr):
        protocol = ServerFactory.buildProtocol(self, addr)
        self.reactor.callLater(0, self.result.callback, protocol)
        return protocol



class _SimplePullProducer(object):
    """
    A pull producer which writes one byte whenever it is resumed.  For use by
    C{test_unregisterProducerAfterDisconnect}.
    """
    def __init__(self, consumer):
        self.consumer = consumer


    def stopProducing(self):
        pass


    def resumeProducing(self):
        log.msg("Producer.resumeProducing")
        self.consumer.write(b'x')



class Stop(ClientFactory):
    """
    A client factory which stops a reactor when a connection attempt fails.
    """
    failReason = None

    def __init__(self, reactor):
        self.reactor = reactor


    def clientConnectionFailed(self, connector, reason):
        self.failReason = reason
        msg("Stop(CF) cCFailed: %s" % (reason.getErrorMessage(),))
        self.reactor.stop()



class ClosingLaterProtocol(ConnectableProtocol):
    """
    ClosingLaterProtocol exchanges one byte with its peer and then disconnects
    itself.  This is mostly a work-around for the fact that connectionMade is
    called before the SSL handshake has completed.
    """
    def __init__(self, onConnectionLost):
        self.lostConnectionReason = None
        self.onConnectionLost = onConnectionLost


    def connectionMade(self):
        msg("ClosingLaterProtocol.connectionMade")


    def dataReceived(self, bytes):
        msg("ClosingLaterProtocol.dataReceived %r" % (bytes,))
        self.transport.loseConnection()


    def connectionLost(self, reason):
        msg("ClosingLaterProtocol.connectionLost")
        self.lostConnectionReason = reason
        self.onConnectionLost.callback(self)



class ConnectionTestsMixin(object):
    """
    This mixin defines test methods which should apply to most L{ITransport}
    implementations.
    """

    # This should be a reactormixins.EndpointCreator instance.
    endpoints = None


    def test_logPrefix(self):
        """
        Client and server transports implement L{ILoggingContext.logPrefix} to
        return a message reflecting the protocol they are running.
        """
        class CustomLogPrefixProtocol(ConnectableProtocol):
            def __init__(self, prefix):
                self._prefix = prefix
                self.system = None

            def connectionMade(self):
                self.transport.write(b"a")

            def logPrefix(self):
                return self._prefix

            def dataReceived(self, bytes):
                self.system = context.get(ILogContext)["system"]
                self.transport.write(b"b")
                # Only close connection if both sides have received data, so
                # that both sides have system set.
                if b"b" in bytes:
                    self.transport.loseConnection()

        client = CustomLogPrefixProtocol("Custom Client")
        server = CustomLogPrefixProtocol("Custom Server")
        runProtocolsWithReactor(self, server, client, self.endpoints)
        self.assertIn("Custom Client", client.system)
        self.assertIn("Custom Server", server.system)


    def test_writeAfterDisconnect(self):
        """
        After a connection is disconnected, L{ITransport.write} and
        L{ITransport.writeSequence} are no-ops.
        """
        reactor = self.buildReactor()

        finished = []

        serverConnectionLostDeferred = Deferred()
        protocol = lambda: ClosingLaterProtocol(serverConnectionLostDeferred)
        portDeferred = self.endpoints.server(reactor).listen(
            ServerFactory.forProtocol(protocol))
        def listening(port):
            msg("Listening on %r" % (port.getHost(),))
            endpoint = self.endpoints.client(reactor, port.getHost())

            lostConnectionDeferred = Deferred()
            protocol = lambda: ClosingLaterProtocol(lostConnectionDeferred)
            client = endpoint.connect(ClientFactory.forProtocol(protocol))
            def write(proto):
                msg("About to write to %r" % (proto,))
                proto.transport.write(b'x')
            client.addCallbacks(write, lostConnectionDeferred.errback)

            def disconnected(proto):
                msg("%r disconnected" % (proto,))
                proto.transport.write(b"some bytes to get lost")
                proto.transport.writeSequence([b"some", b"more"])
                finished.append(True)

            lostConnectionDeferred.addCallback(disconnected)
            serverConnectionLostDeferred.addCallback(disconnected)
            return gatherResults([lostConnectionDeferred,
                                  serverConnectionLostDeferred])

        def onListen():
            portDeferred.addCallback(listening)
            portDeferred.addErrback(err)
            portDeferred.addCallback(lambda ignored: reactor.stop())
        needsRunningReactor(reactor, onListen)

        self.runReactor(reactor)
        self.assertEqual(finished, [True, True])


    def test_protocolGarbageAfterLostConnection(self):
        """
        After the connection a protocol is being used for is closed, the
        reactor discards all of its references to the protocol.
        """
        lostConnectionDeferred = Deferred()
        clientProtocol = ClosingLaterProtocol(lostConnectionDeferred)
        clientRef = ref(clientProtocol)

        reactor = self.buildReactor()
        portDeferred = self.endpoints.server(reactor).listen(
            ServerFactory.forProtocol(Protocol))
        def listening(port):
            msg("Listening on %r" % (port.getHost(),))
            endpoint = self.endpoints.client(reactor, port.getHost())

            client = endpoint.connect(
                ClientFactory.forProtocol(lambda: clientProtocol))
            def disconnect(proto):
                msg("About to disconnect %r" % (proto,))
                proto.transport.loseConnection()
            client.addCallback(disconnect)
            client.addErrback(lostConnectionDeferred.errback)
            return lostConnectionDeferred

        def onListening():
            portDeferred.addCallback(listening)
            portDeferred.addErrback(err)
            portDeferred.addBoth(lambda ignored: reactor.stop())
        needsRunningReactor(reactor, onListening)

        self.runReactor(reactor)

        # Drop the reference and get the garbage collector to tell us if there
        # are no references to the protocol instance left in the reactor.
        clientProtocol = None
        collect()
        self.assertIsNone(clientRef())



class LogObserverMixin(object):
    """
    Mixin for L{TestCase} subclasses which want to observe log events.
    """
    def observe(self):
        loggedMessages = []
        log.addObserver(loggedMessages.append)
        self.addCleanup(log.removeObserver, loggedMessages.append)
        return loggedMessages



class BrokenContextFactory(object):
    """
    A context factory with a broken C{getContext} method, for exercising the
    error handling for such a case.
    """
    message = "Some path was wrong maybe"

    def getContext(self):
        raise ValueError(self.message)



class StreamClientTestsMixin(object):
    """
    This mixin defines tests applicable to SOCK_STREAM client implementations.

    This must be mixed in to a L{ReactorBuilder
    <twisted.internet.test.reactormixins.ReactorBuilder>} subclass, as it
    depends on several of its methods.

    Then the methods C{connect} and C{listen} must defined, defining a client
    and a server communicating with each other.
    """

    def test_interface(self):
        """
        The C{connect} method returns an object providing L{IConnector}.
        """
        reactor = self.buildReactor()
        connector = self.connect(reactor, ClientFactory())
        self.assertTrue(verifyObject(IConnector, connector))


    def test_clientConnectionFailedStopsReactor(self):
        """
        The reactor can be stopped by a client factory's
        C{clientConnectionFailed} method.
        """
        reactor = self.buildReactor()
        needsRunningReactor(
            reactor, lambda: self.connect(reactor, Stop(reactor)))
        self.runReactor(reactor)


    def test_connectEvent(self):
        """
        This test checks that we correctly get notifications event for a
        client.  This ought to prevent a regression under Windows using the
        GTK2 reactor.  See #3925.
        """
        reactor = self.buildReactor()

        self.listen(reactor, ServerFactory.forProtocol(Protocol))
        connected = []

        class CheckConnection(Protocol):

            def connectionMade(self):
                connected.append(self)
                reactor.stop()

        clientFactory = Stop(reactor)
        clientFactory.protocol = CheckConnection

        needsRunningReactor(
            reactor, lambda: self.connect(reactor, clientFactory))

        reactor.run()

        self.assertTrue(connected)


    def test_unregisterProducerAfterDisconnect(self):
        """
        If a producer is unregistered from a transport after the transport has
        been disconnected (by the peer) and after C{loseConnection} has been
        called, the transport is not re-added to the reactor as a writer as
        would be necessary if the transport were still connected.
        """
        reactor = self.buildReactor()
        self.listen(reactor, ServerFactory.forProtocol(ClosingProtocol))

        finished = Deferred()
        finished.addErrback(log.err)
        finished.addCallback(lambda ign: reactor.stop())

        writing = []

        class ClientProtocol(Protocol):
            """
            Protocol to connect, register a producer, try to lose the
            connection, wait for the server to disconnect from us, and then
            unregister the producer.
            """

            def connectionMade(self):
                log.msg("ClientProtocol.connectionMade")
                self.transport.registerProducer(
                    _SimplePullProducer(self.transport), False)
                self.transport.loseConnection()

            def connectionLost(self, reason):
                log.msg("ClientProtocol.connectionLost")
                self.unregister()
                writing.append(self.transport in _getWriters(reactor))
                finished.callback(None)

            def unregister(self):
                log.msg("ClientProtocol unregister")
                self.transport.unregisterProducer()

        clientFactory = ClientFactory()
        clientFactory.protocol = ClientProtocol
        self.connect(reactor, clientFactory)
        self.runReactor(reactor)
        self.assertFalse(writing[0],
                         "Transport was writing after unregisterProducer.")


    def test_disconnectWhileProducing(self):
        """
        If C{loseConnection} is called while a producer is registered with the
        transport, the connection is closed after the producer is unregistered.
        """
        reactor = self.buildReactor()

        # For some reason, pyobject/pygtk will not deliver the close
        # notification that should happen after the unregisterProducer call in
        # this test.  The selectable is in the write notification set, but no
        # notification ever arrives.  Probably for the same reason #5233 led
        # win32eventreactor to be broken.
        skippedReactors = ["Glib2Reactor", "Gtk2Reactor"]
        reactorClassName = reactor.__class__.__name__
        if reactorClassName in skippedReactors and platform.isWindows():
            raise SkipTest(
                "A pygobject/pygtk bug disables this functionality "
                "on Windows.")

        class Producer:
            def resumeProducing(self):
                log.msg("Producer.resumeProducing")

        self.listen(reactor, ServerFactory.forProtocol(Protocol))

        finished = Deferred()
        finished.addErrback(log.err)
        finished.addCallback(lambda ign: reactor.stop())

        class ClientProtocol(Protocol):
            """
            Protocol to connect, register a producer, try to lose the
            connection, unregister the producer, and wait for the connection to
            actually be lost.
            """
            def connectionMade(self):
                log.msg("ClientProtocol.connectionMade")
                self.transport.registerProducer(Producer(), False)
                self.transport.loseConnection()
                # Let the reactor tick over, in case synchronously calling
                # loseConnection and then unregisterProducer is the same as
                # synchronously calling unregisterProducer and then
                # loseConnection (as it is in several reactors).
                reactor.callLater(0, reactor.callLater, 0, self.unregister)

            def unregister(self):
                log.msg("ClientProtocol unregister")
                self.transport.unregisterProducer()
                # This should all be pretty quick.  Fail the test
                # if we don't get a connectionLost event really
                # soon.
                reactor.callLater(
                    1.0, finished.errback,
                    Failure(Exception("Connection was not lost")))

            def connectionLost(self, reason):
                log.msg("ClientProtocol.connectionLost")
                finished.callback(None)

        clientFactory = ClientFactory()
        clientFactory.protocol = ClientProtocol
        self.connect(reactor, clientFactory)
        self.runReactor(reactor)
        # If the test failed, we logged an error already and trial
        # will catch it.
