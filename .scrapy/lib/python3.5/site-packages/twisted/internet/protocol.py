# -*- test-case-name: twisted.test.test_factories,twisted.internet.test.test_protocol -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Standard implementations of Twisted protocol-related interfaces.

Start here if you are looking to write a new protocol implementation for
Twisted.  The Protocol class contains some introductory material.
"""

from __future__ import division, absolute_import

import random
from zope.interface import implementer

from twisted.python import log, failure, components
from twisted.internet import interfaces, error, defer
from twisted.logger import _loggerFor


@implementer(interfaces.IProtocolFactory, interfaces.ILoggingContext)
class Factory:
    """
    This is a factory which produces protocols.

    By default, buildProtocol will create a protocol of the class given in
    self.protocol.
    """

    # put a subclass of Protocol here:
    protocol = None

    numPorts = 0
    noisy = True

    @classmethod
    def forProtocol(cls, protocol, *args, **kwargs):
        """
        Create a factory for the given protocol.

        It sets the C{protocol} attribute and returns the constructed factory
        instance.

        @param protocol: A L{Protocol} subclass

        @param args: Positional arguments for the factory.

        @param kwargs: Keyword arguments for the factory.

        @return: A L{Factory} instance wired up to C{protocol}.
        """
        factory = cls(*args, **kwargs)
        factory.protocol = protocol
        return factory


    def logPrefix(self):
        """
        Describe this factory for log messages.
        """
        return self.__class__.__name__


    def doStart(self):
        """Make sure startFactory is called.

        Users should not call this function themselves!
        """
        if not self.numPorts:
            if self.noisy:
                _loggerFor(self).info("Starting factory {factory!r}",
                                      factory=self)
            self.startFactory()
        self.numPorts = self.numPorts + 1

    def doStop(self):
        """Make sure stopFactory is called.

        Users should not call this function themselves!
        """
        if self.numPorts == 0:
            # this shouldn't happen, but does sometimes and this is better
            # than blowing up in assert as we did previously.
            return
        self.numPorts = self.numPorts - 1
        if not self.numPorts:
            if self.noisy:
                _loggerFor(self).info("Stopping factory {factory!r}",
                                      factory=self)
            self.stopFactory()

    def startFactory(self):
        """This will be called before I begin listening on a Port or Connector.

        It will only be called once, even if the factory is connected
        to multiple ports.

        This can be used to perform 'unserialization' tasks that
        are best put off until things are actually running, such
        as connecting to a database, opening files, etcetera.
        """

    def stopFactory(self):
        """This will be called before I stop listening on all Ports/Connectors.

        This can be overridden to perform 'shutdown' tasks such as disconnecting
        database connections, closing files, etc.

        It will be called, for example, before an application shuts down,
        if it was connected to a port. User code should not call this function
        directly.
        """


    def buildProtocol(self, addr):
        """
        Create an instance of a subclass of Protocol.

        The returned instance will handle input on an incoming server
        connection, and an attribute "factory" pointing to the creating
        factory.

        Alternatively, L{None} may be returned to immediately close the
        new connection.

        Override this method to alter how Protocol instances get created.

        @param addr: an object implementing L{twisted.internet.interfaces.IAddress}
        """
        p = self.protocol()
        p.factory = self
        return p



class ClientFactory(Factory):
    """A Protocol factory for clients.

    This can be used together with the various connectXXX methods in
    reactors.
    """

    def startedConnecting(self, connector):
        """Called when a connection has been started.

        You can call connector.stopConnecting() to stop the connection attempt.

        @param connector: a Connector object.
        """

    def clientConnectionFailed(self, connector, reason):
        """Called when a connection has failed to connect.

        It may be useful to call connector.connect() - this will reconnect.

        @type reason: L{twisted.python.failure.Failure}
        """

    def clientConnectionLost(self, connector, reason):
        """Called when an established connection is lost.

        It may be useful to call connector.connect() - this will reconnect.

        @type reason: L{twisted.python.failure.Failure}
        """


class _InstanceFactory(ClientFactory):
    """
    Factory used by ClientCreator.

    @ivar deferred: The L{Deferred} which represents this connection attempt and
        which will be fired when it succeeds or fails.

    @ivar pending: After a connection attempt succeeds or fails, a delayed call
        which will fire the L{Deferred} representing this connection attempt.
    """

    noisy = False
    pending = None

    def __init__(self, reactor, instance, deferred):
        self.reactor = reactor
        self.instance = instance
        self.deferred = deferred


    def __repr__(self):
        return "<ClientCreator factory: %r>" % (self.instance, )


    def buildProtocol(self, addr):
        """
        Return the pre-constructed protocol instance and arrange to fire the
        waiting L{Deferred} to indicate success establishing the connection.
        """
        self.pending = self.reactor.callLater(
            0, self.fire, self.deferred.callback, self.instance)
        self.deferred = None
        return self.instance


    def clientConnectionFailed(self, connector, reason):
        """
        Arrange to fire the waiting L{Deferred} with the given failure to
        indicate the connection could not be established.
        """
        self.pending = self.reactor.callLater(
            0, self.fire, self.deferred.errback, reason)
        self.deferred = None


    def fire(self, func, value):
        """
        Clear C{self.pending} to avoid a reference cycle and then invoke func
        with the value.
        """
        self.pending = None
        func(value)



class ClientCreator:
    """
    Client connections that do not require a factory.

    The various connect* methods create a protocol instance using the given
    protocol class and arguments, and connect it, returning a Deferred of the
    resulting protocol instance.

    Useful for cases when we don't really need a factory.  Mainly this
    is when there is no shared state between protocol instances, and no need
    to reconnect.

    The C{connectTCP}, C{connectUNIX}, and C{connectSSL} methods each return a
    L{Deferred} which will fire with an instance of the protocol class passed to
    L{ClientCreator.__init__}.  These Deferred can be cancelled to abort the
    connection attempt (in a very unlikely case, cancelling the Deferred may not
    prevent the protocol from being instantiated and connected to a transport;
    if this happens, it will be disconnected immediately afterwards and the
    Deferred will still errback with L{CancelledError}).
    """

    def __init__(self, reactor, protocolClass, *args, **kwargs):
        self.reactor = reactor
        self.protocolClass = protocolClass
        self.args = args
        self.kwargs = kwargs


    def _connect(self, method, *args, **kwargs):
        """
        Initiate a connection attempt.

        @param method: A callable which will actually start the connection
            attempt.  For example, C{reactor.connectTCP}.

        @param *args: Positional arguments to pass to C{method}, excluding the
            factory.

        @param **kwargs: Keyword arguments to pass to C{method}.

        @return: A L{Deferred} which fires with an instance of the protocol
            class passed to this L{ClientCreator}'s initializer or fails if the
            connection cannot be set up for some reason.
        """
        def cancelConnect(deferred):
            connector.disconnect()
            if f.pending is not None:
                f.pending.cancel()
        d = defer.Deferred(cancelConnect)
        f = _InstanceFactory(
            self.reactor, self.protocolClass(*self.args, **self.kwargs), d)
        connector = method(factory=f, *args, **kwargs)
        return d


    def connectTCP(self, host, port, timeout=30, bindAddress=None):
        """
        Connect to a TCP server.

        The parameters are all the same as to L{IReactorTCP.connectTCP} except
        that the factory parameter is omitted.

        @return: A L{Deferred} which fires with an instance of the protocol
            class passed to this L{ClientCreator}'s initializer or fails if the
            connection cannot be set up for some reason.
        """
        return self._connect(
            self.reactor.connectTCP, host, port, timeout=timeout,
            bindAddress=bindAddress)


    def connectUNIX(self, address, timeout=30, checkPID=False):
        """
        Connect to a Unix socket.

        The parameters are all the same as to L{IReactorUNIX.connectUNIX} except
        that the factory parameter is omitted.

        @return: A L{Deferred} which fires with an instance of the protocol
            class passed to this L{ClientCreator}'s initializer or fails if the
            connection cannot be set up for some reason.
        """
        return self._connect(
            self.reactor.connectUNIX, address, timeout=timeout,
            checkPID=checkPID)


    def connectSSL(self, host, port, contextFactory, timeout=30, bindAddress=None):
        """
        Connect to an SSL server.

        The parameters are all the same as to L{IReactorSSL.connectSSL} except
        that the factory parameter is omitted.

        @return: A L{Deferred} which fires with an instance of the protocol
            class passed to this L{ClientCreator}'s initializer or fails if the
            connection cannot be set up for some reason.
        """
        return self._connect(
            self.reactor.connectSSL, host, port,
            contextFactory=contextFactory, timeout=timeout,
            bindAddress=bindAddress)



class ReconnectingClientFactory(ClientFactory):
    """
    Factory which auto-reconnects clients with an exponential back-off.

    Note that clients should call my resetDelay method after they have
    connected successfully.

    @ivar maxDelay: Maximum number of seconds between connection attempts.
    @ivar initialDelay: Delay for the first reconnection attempt.
    @ivar factor: A multiplicitive factor by which the delay grows
    @ivar jitter: Percentage of randomness to introduce into the delay length
        to prevent stampeding.
    @ivar clock: The clock used to schedule reconnection. It's mainly useful to
        be parametrized in tests. If the factory is serialized, this attribute
        will not be serialized, and the default value (the reactor) will be
        restored when deserialized.
    @type clock: L{IReactorTime}
    @ivar maxRetries: Maximum number of consecutive unsuccessful connection
        attempts, after which no further connection attempts will be made. If
        this is not explicitly set, no maximum is applied.
    """
    maxDelay = 3600
    initialDelay = 1.0
    # Note: These highly sensitive factors have been precisely measured by
    # the National Institute of Science and Technology.  Take extreme care
    # in altering them, or you may damage your Internet!
    # (Seriously: <http://physics.nist.gov/cuu/Constants/index.html>)
    factor = 2.7182818284590451 # (math.e)
    # Phi = 1.6180339887498948 # (Phi is acceptable for use as a
    # factor if e is too large for your application.)
    jitter = 0.11962656472 # molar Planck constant times c, joule meter/mole

    delay = initialDelay
    retries = 0
    maxRetries = None
    _callID = None
    connector = None
    clock = None

    continueTrying = 1


    def clientConnectionFailed(self, connector, reason):
        if self.continueTrying:
            self.connector = connector
            self.retry()


    def clientConnectionLost(self, connector, unused_reason):
        if self.continueTrying:
            self.connector = connector
            self.retry()


    def retry(self, connector=None):
        """
        Have this connector connect again, after a suitable delay.
        """
        if not self.continueTrying:
            if self.noisy:
                log.msg("Abandoning %s on explicit request" % (connector,))
            return

        if connector is None:
            if self.connector is None:
                raise ValueError("no connector to retry")
            else:
                connector = self.connector

        self.retries += 1
        if self.maxRetries is not None and (self.retries > self.maxRetries):
            if self.noisy:
                log.msg("Abandoning %s after %d retries." %
                        (connector, self.retries))
            return

        self.delay = min(self.delay * self.factor, self.maxDelay)
        if self.jitter:
            self.delay = random.normalvariate(self.delay,
                                              self.delay * self.jitter)

        if self.noisy:
            log.msg("%s will retry in %d seconds" % (connector, self.delay,))

        def reconnector():
            self._callID = None
            connector.connect()
        if self.clock is None:
            from twisted.internet import reactor
            self.clock = reactor
        self._callID = self.clock.callLater(self.delay, reconnector)


    def stopTrying(self):
        """
        Put a stop to any attempt to reconnect in progress.
        """
        # ??? Is this function really stopFactory?
        if self._callID:
            self._callID.cancel()
            self._callID = None
        self.continueTrying = 0
        if self.connector:
            try:
                self.connector.stopConnecting()
            except error.NotConnectingError:
                pass


    def resetDelay(self):
        """
        Call this method after a successful connection: it resets the delay and
        the retry counter.
        """
        self.delay = self.initialDelay
        self.retries = 0
        self._callID = None
        self.continueTrying = 1


    def __getstate__(self):
        """
        Remove all of the state which is mutated by connection attempts and
        failures, returning just the state which describes how reconnections
        should be attempted.  This will make the unserialized instance
        behave just as this one did when it was first instantiated.
        """
        state = self.__dict__.copy()
        for key in ['connector', 'retries', 'delay',
                    'continueTrying', '_callID', 'clock']:
            if key in state:
                del state[key]
        return state



class ServerFactory(Factory):
    """Subclass this to indicate that your protocol.Factory is only usable for servers.
    """



class BaseProtocol:
    """
    This is the abstract superclass of all protocols.

    Some methods have helpful default implementations here so that they can
    easily be shared, but otherwise the direct subclasses of this class are more
    interesting, L{Protocol} and L{ProcessProtocol}.
    """
    connected = 0
    transport = None

    def makeConnection(self, transport):
        """Make a connection to a transport and a server.

        This sets the 'transport' attribute of this Protocol, and calls the
        connectionMade() callback.
        """
        self.connected = 1
        self.transport = transport
        self.connectionMade()

    def connectionMade(self):
        """Called when a connection is made.

        This may be considered the initializer of the protocol, because
        it is called when the connection is completed.  For clients,
        this is called once the connection to the server has been
        established; for servers, this is called after an accept() call
        stops blocking and a socket has been received.  If you need to
        send any greeting or initial message, do it here.
        """

connectionDone=failure.Failure(error.ConnectionDone())
connectionDone.cleanFailure()


@implementer(interfaces.IProtocol, interfaces.ILoggingContext)
class Protocol(BaseProtocol):
    """
    This is the base class for streaming connection-oriented protocols.

    If you are going to write a new connection-oriented protocol for Twisted,
    start here.  Any protocol implementation, either client or server, should
    be a subclass of this class.

    The API is quite simple.  Implement L{dataReceived} to handle both
    event-based and synchronous input; output can be sent through the
    'transport' attribute, which is to be an instance that implements
    L{twisted.internet.interfaces.ITransport}.  Override C{connectionLost} to be
    notified when the connection ends.

    Some subclasses exist already to help you write common types of protocols:
    see the L{twisted.protocols.basic} module for a few of them.
    """

    def logPrefix(self):
        """
        Return a prefix matching the class name, to identify log messages
        related to this protocol instance.
        """
        return self.__class__.__name__


    def dataReceived(self, data):
        """Called whenever data is received.

        Use this method to translate to a higher-level message.  Usually, some
        callback will be made upon the receipt of each complete protocol
        message.

        @param data: a string of indeterminate length.  Please keep in mind
            that you will probably need to buffer some data, as partial
            (or multiple) protocol messages may be received!  I recommend
            that unit tests for protocols call through to this method with
            differing chunk sizes, down to one byte at a time.
        """

    def connectionLost(self, reason=connectionDone):
        """Called when the connection is shut down.

        Clear any circular references here, and any external references
        to this Protocol.  The connection has been closed.

        @type reason: L{twisted.python.failure.Failure}
        """


@implementer(interfaces.IConsumer)
class ProtocolToConsumerAdapter(components.Adapter):

    def write(self, data):
        self.original.dataReceived(data)

    def registerProducer(self, producer, streaming):
        pass

    def unregisterProducer(self):
        pass

components.registerAdapter(ProtocolToConsumerAdapter, interfaces.IProtocol,
                           interfaces.IConsumer)

@implementer(interfaces.IProtocol)
class ConsumerToProtocolAdapter(components.Adapter):

    def dataReceived(self, data):
        self.original.write(data)

    def connectionLost(self, reason):
        pass

    def makeConnection(self, transport):
        pass

    def connectionMade(self):
        pass

components.registerAdapter(ConsumerToProtocolAdapter, interfaces.IConsumer,
                           interfaces.IProtocol)

@implementer(interfaces.IProcessProtocol)
class ProcessProtocol(BaseProtocol):
    """
    Base process protocol implementation which does simple dispatching for
    stdin, stdout, and stderr file descriptors.
    """

    def childDataReceived(self, childFD, data):
        if childFD == 1:
            self.outReceived(data)
        elif childFD == 2:
            self.errReceived(data)


    def outReceived(self, data):
        """
        Some data was received from stdout.
        """


    def errReceived(self, data):
        """
        Some data was received from stderr.
        """


    def childConnectionLost(self, childFD):
        if childFD == 0:
            self.inConnectionLost()
        elif childFD == 1:
            self.outConnectionLost()
        elif childFD == 2:
            self.errConnectionLost()


    def inConnectionLost(self):
        """
        This will be called when stdin is closed.
        """


    def outConnectionLost(self):
        """
        This will be called when stdout is closed.
        """


    def errConnectionLost(self):
        """
        This will be called when stderr is closed.
        """


    def processExited(self, reason):
        """
        This will be called when the subprocess exits.

        @type reason: L{twisted.python.failure.Failure}
        """


    def processEnded(self, reason):
        """
        Called when the child process exits and all file descriptors
        associated with it have been closed.

        @type reason: L{twisted.python.failure.Failure}
        """



class AbstractDatagramProtocol:
    """
    Abstract protocol for datagram-oriented transports, e.g. IP, ICMP, ARP, UDP.
    """

    transport = None
    numPorts = 0
    noisy = True

    def __getstate__(self):
        d = self.__dict__.copy()
        d['transport'] = None
        return d

    def doStart(self):
        """Make sure startProtocol is called.

        This will be called by makeConnection(), users should not call it.
        """
        if not self.numPorts:
            if self.noisy:
                log.msg("Starting protocol %s" % self)
            self.startProtocol()
        self.numPorts = self.numPorts + 1

    def doStop(self):
        """Make sure stopProtocol is called.

        This will be called by the port, users should not call it.
        """
        assert self.numPorts > 0
        self.numPorts = self.numPorts - 1
        self.transport = None
        if not self.numPorts:
            if self.noisy:
                log.msg("Stopping protocol %s" % self)
            self.stopProtocol()

    def startProtocol(self):
        """Called when a transport is connected to this protocol.

        Will only be called once, even if multiple ports are connected.
        """

    def stopProtocol(self):
        """Called when the transport is disconnected.

        Will only be called once, after all ports are disconnected.
        """

    def makeConnection(self, transport):
        """Make a connection to a transport and a server.

        This sets the 'transport' attribute of this DatagramProtocol, and calls the
        doStart() callback.
        """
        assert self.transport == None
        self.transport = transport
        self.doStart()

    def datagramReceived(self, datagram, addr):
        """Called when a datagram is received.

        @param datagram: the string received from the transport.
        @param addr: tuple of source of datagram.
        """


@implementer(interfaces.ILoggingContext)
class DatagramProtocol(AbstractDatagramProtocol):
    """
    Protocol for datagram-oriented transport, e.g. UDP.

    @type transport: L{None} or
        L{IUDPTransport<twisted.internet.interfaces.IUDPTransport>} provider
    @ivar transport: The transport with which this protocol is associated,
        if it is associated with one.
    """

    def logPrefix(self):
        """
        Return a prefix matching the class name, to identify log messages
        related to this protocol instance.
        """
        return self.__class__.__name__


    def connectionRefused(self):
        """Called due to error from write in connected mode.

        Note this is a result of ICMP message generated by *previous*
        write.
        """


class ConnectedDatagramProtocol(DatagramProtocol):
    """Protocol for connected datagram-oriented transport.

    No longer necessary for UDP.
    """

    def datagramReceived(self, datagram):
        """Called when a datagram is received.

        @param datagram: the string received from the transport.
        """

    def connectionFailed(self, failure):
        """Called if connecting failed.

        Usually this will be due to a DNS lookup failure.
        """



@implementer(interfaces.ITransport)
class FileWrapper:
    """A wrapper around a file-like object to make it behave as a Transport.

    This doesn't actually stream the file to the attached protocol,
    and is thus useful mainly as a utility for debugging protocols.
    """

    closed = 0
    disconnecting = 0
    producer = None
    streamingProducer = 0

    def __init__(self, file):
        self.file = file

    def write(self, data):
        try:
            self.file.write(data)
        except:
            self.handleException()
        # self._checkProducer()

    def _checkProducer(self):
        # Cheating; this is called at "idle" times to allow producers to be
        # found and dealt with
        if self.producer:
            self.producer.resumeProducing()

    def registerProducer(self, producer, streaming):
        """From abstract.FileDescriptor
        """
        self.producer = producer
        self.streamingProducer = streaming
        if not streaming:
            producer.resumeProducing()

    def unregisterProducer(self):
        self.producer = None

    def stopConsuming(self):
        self.unregisterProducer()
        self.loseConnection()

    def writeSequence(self, iovec):
        self.write("".join(iovec))

    def loseConnection(self):
        self.closed = 1
        try:
            self.file.close()
        except (IOError, OSError):
            self.handleException()

    def getPeer(self):
        # FIXME: https://twistedmatrix.com/trac/ticket/7820
        # According to ITransport, this should return an IAddress!
        return 'file', 'file'

    def getHost(self):
        # FIXME: https://twistedmatrix.com/trac/ticket/7820
        # According to ITransport, this should return an IAddress!
        return 'file'

    def handleException(self):
        pass

    def resumeProducing(self):
        # Never sends data anyways
        pass

    def pauseProducing(self):
        # Never sends data anyways
        pass

    def stopProducing(self):
        self.loseConnection()


__all__ = ["Factory", "ClientFactory", "ReconnectingClientFactory", "connectionDone",
           "Protocol", "ProcessProtocol", "FileWrapper", "ServerFactory",
           "AbstractDatagramProtocol", "DatagramProtocol", "ConnectedDatagramProtocol",
           "ClientCreator"]
