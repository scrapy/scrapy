# -*- test-case-name: twisted.internet.test.test_testing -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Assorted functionality which is commonly useful when writing unit tests.
"""


from collections.abc import Sequence
from io import BytesIO
from socket import AF_INET, AF_INET6
from typing import Any, Callable

from zope.interface import implementedBy, implementer
from zope.interface.verify import verifyClass

from twisted.internet import address, error, protocol, task
from twisted.internet.abstract import _dataMustBeBytes, isIPv6Address
from twisted.internet.address import IPv4Address, IPv6Address, UNIXAddress
from twisted.internet.defer import Deferred
from twisted.internet.error import UnsupportedAddressFamily
from twisted.internet.interfaces import (
    IConnector,
    IConsumer,
    IListeningPort,
    IProtocol,
    IPushProducer,
    IReactorCore,
    IReactorFDSet,
    IReactorSocket,
    IReactorSSL,
    IReactorTCP,
    IReactorUNIX,
    ITransport,
)
from twisted.internet.task import Clock
from twisted.logger import ILogObserver
from twisted.protocols import basic
from twisted.python import failure

__all__ = [
    "AccumulatingProtocol",
    "LineSendingProtocol",
    "FakeDatagramTransport",
    "StringTransport",
    "StringTransportWithDisconnection",
    "StringIOWithoutClosing",
    "_FakeConnector",
    "_FakePort",
    "MemoryReactor",
    "MemoryReactorClock",
    "RaisingMemoryReactor",
    "NonStreamingProducer",
    "waitUntilAllDisconnected",
    "EventLoggingObserver",
]


class AccumulatingProtocol(protocol.Protocol):
    """
    L{AccumulatingProtocol} is an L{IProtocol} implementation which collects
    the data delivered to it and can fire a Deferred when it is connected or
    disconnected.

    @ivar made: A flag indicating whether C{connectionMade} has been called.
    @ivar data: Bytes giving all the data passed to C{dataReceived}.
    @ivar closed: A flag indicated whether C{connectionLost} has been called.
    @ivar closedReason: The value of the I{reason} parameter passed to
        C{connectionLost}.
    @ivar closedDeferred: If set to a L{Deferred}, this will be fired when
        C{connectionLost} is called.
    """

    made = closed = 0
    closedReason = None

    closedDeferred = None

    data = b""

    factory = None

    def connectionMade(self):
        self.made = 1
        if self.factory is not None and self.factory.protocolConnectionMade is not None:
            d = self.factory.protocolConnectionMade
            self.factory.protocolConnectionMade = None
            d.callback(self)

    def dataReceived(self, data):
        self.data += data

    def connectionLost(self, reason):
        self.closed = 1
        self.closedReason = reason
        if self.closedDeferred is not None:
            d, self.closedDeferred = self.closedDeferred, None
            d.callback(None)


class LineSendingProtocol(basic.LineReceiver):
    lostConn = False

    def __init__(self, lines, start=True):
        self.lines = lines[:]
        self.response = []
        self.start = start

    def connectionMade(self):
        if self.start:
            for line in self.lines:
                self.sendLine(line)

    def lineReceived(self, line):
        if not self.start:
            for line in self.lines:
                self.sendLine(line)
            self.lines = []
        self.response.append(line)

    def connectionLost(self, reason):
        self.lostConn = True


class FakeDatagramTransport:
    noAddr = object()

    def __init__(self):
        self.written = []

    def write(self, packet, addr=noAddr):
        self.written.append((packet, addr))


@implementer(ITransport, IConsumer, IPushProducer)
class StringTransport:
    """
    A transport implementation which buffers data in memory and keeps track of
    its other state without providing any behavior.

    L{StringTransport} has a number of attributes which are not part of any of
    the interfaces it claims to implement.  These attributes are provided for
    testing purposes.  Implementation code should not use any of these
    attributes; they are not provided by other transports.

    @ivar disconnecting: A C{bool} which is C{False} until L{loseConnection} is
        called, then C{True}.

    @ivar disconnected: A C{bool} which is C{False} until L{abortConnection} is
        called, then C{True}.

    @ivar producer: If a producer is currently registered, C{producer} is a
        reference to it.  Otherwise, L{None}.

    @ivar streaming: If a producer is currently registered, C{streaming} refers
        to the value of the second parameter passed to C{registerProducer}.

    @ivar hostAddr: L{None} or an object which will be returned as the host
        address of this transport.  If L{None}, a nasty tuple will be returned
        instead.

    @ivar peerAddr: L{None} or an object which will be returned as the peer
        address of this transport.  If L{None}, a nasty tuple will be returned
        instead.

    @ivar producerState: The state of this L{StringTransport} in its capacity
        as an L{IPushProducer}.  One of C{'producing'}, C{'paused'}, or
        C{'stopped'}.

    @ivar io: A L{io.BytesIO} which holds the data which has been written to
        this transport since the last call to L{clear}.  Use L{value} instead
        of accessing this directly.

    @ivar _lenient: By default L{StringTransport} enforces that
        L{resumeProducing} is not called after the connection is lost. This is
        to ensure that any code that does call L{resumeProducing} after the
        connection is lost is not blindly expecting L{resumeProducing} to have
        any impact.

        However, if your test case is calling L{resumeProducing} after
        connection close on purpose, and you know it won't block expecting
        further data to show up, this flag may safely be set to L{True}.

        Defaults to L{False}.
    @type lenient: L{bool}
    """

    disconnecting = False
    disconnected = False

    producer = None
    streaming = None

    hostAddr = None
    peerAddr = None

    producerState = "producing"

    def __init__(self, hostAddress=None, peerAddress=None, lenient=False):
        self.clear()
        if hostAddress is not None:
            self.hostAddr = hostAddress
        if peerAddress is not None:
            self.peerAddr = peerAddress
        self.connected = True
        self._lenient = lenient

    def clear(self):
        """
        Discard all data written to this transport so far.

        This is not a transport method.  It is intended for tests.  Do not use
        it in implementation code.
        """
        self.io = BytesIO()

    def value(self):
        """
        Retrieve all data which has been buffered by this transport.

        This is not a transport method.  It is intended for tests.  Do not use
        it in implementation code.

        @return: A C{bytes} giving all data written to this transport since the
            last call to L{clear}.
        @rtype: C{bytes}
        """
        return self.io.getvalue()

    # ITransport
    def write(self, data):
        _dataMustBeBytes(data)
        self.io.write(data)

    def writeSequence(self, data):
        self.io.write(b"".join(data))

    def loseConnection(self):
        """
        Close the connection. Does nothing besides toggle the C{disconnecting}
        instance variable to C{True}.
        """
        self.disconnecting = True

    def abortConnection(self):
        """
        Abort the connection. Same as C{loseConnection}, but also toggles the
        C{aborted} instance variable to C{True}.
        """
        self.disconnected = True
        self.loseConnection()

    def getPeer(self):
        if self.peerAddr is None:
            return address.IPv4Address("TCP", "192.168.1.1", 54321)
        return self.peerAddr

    def getHost(self):
        if self.hostAddr is None:
            return address.IPv4Address("TCP", "10.0.0.1", 12345)
        return self.hostAddr

    # IConsumer
    def registerProducer(self, producer, streaming):
        if self.producer is not None:
            raise RuntimeError("Cannot register two producers")
        self.producer = producer
        self.streaming = streaming

    def unregisterProducer(self):
        if self.producer is None:
            raise RuntimeError("Cannot unregister a producer unless one is registered")
        self.producer = None
        self.streaming = None

    # IPushProducer
    def _checkState(self):
        if self.disconnecting and not self._lenient:
            raise RuntimeError("Cannot resume producing after loseConnection")
        if self.producerState == "stopped":
            raise RuntimeError("Cannot resume a stopped producer")

    def pauseProducing(self):
        self._checkState()
        self.producerState = "paused"

    def stopProducing(self):
        self.producerState = "stopped"

    def resumeProducing(self):
        self._checkState()
        self.producerState = "producing"


class StringTransportWithDisconnection(StringTransport):
    """
    A L{StringTransport} which on disconnection will trigger the connection
    lost on the attached protocol.
    """

    protocol: IProtocol

    def loseConnection(self):
        if self.connected:
            self.connected = False
            self.protocol.connectionLost(failure.Failure(error.ConnectionDone("Bye.")))


class StringIOWithoutClosing(BytesIO):
    """
    A BytesIO that can't be closed.
    """

    def close(self):
        """
        Do nothing.
        """


@implementer(IListeningPort)
class _FakePort:
    """
    A fake L{IListeningPort} to be used in tests.

    @ivar _hostAddress: The L{IAddress} this L{IListeningPort} is pretending
        to be listening on.
    """

    def __init__(self, hostAddress):
        """
        @param hostAddress: An L{IAddress} this L{IListeningPort} should
            pretend to be listening on.
        """
        self._hostAddress = hostAddress

    def startListening(self):
        """
        Fake L{IListeningPort.startListening} that doesn't do anything.
        """

    def stopListening(self):
        """
        Fake L{IListeningPort.stopListening} that doesn't do anything.
        """

    def getHost(self):
        """
        Fake L{IListeningPort.getHost} that returns our L{IAddress}.
        """
        return self._hostAddress


@implementer(IConnector)
class _FakeConnector:
    """
    A fake L{IConnector} that allows us to inspect if it has been told to stop
    connecting.

    @ivar stoppedConnecting: has this connector's
        L{_FakeConnector.stopConnecting} method been invoked yet?

    @ivar _address: An L{IAddress} provider that represents our destination.
    """

    _disconnected = False
    stoppedConnecting = False

    def __init__(self, address):
        """
        @param address: An L{IAddress} provider that represents this
            connector's destination.
        """
        self._address = address

    def stopConnecting(self):
        """
        Implement L{IConnector.stopConnecting} and set
        L{_FakeConnector.stoppedConnecting} to C{True}
        """
        self.stoppedConnecting = True

    def disconnect(self):
        """
        Implement L{IConnector.disconnect} as a no-op.
        """
        self._disconnected = True

    def connect(self):
        """
        Implement L{IConnector.connect} as a no-op.
        """

    def getDestination(self):
        """
        Implement L{IConnector.getDestination} to return the C{address} passed
        to C{__init__}.
        """
        return self._address


@implementer(
    IReactorCore, IReactorTCP, IReactorSSL, IReactorUNIX, IReactorSocket, IReactorFDSet
)
class MemoryReactor:
    """
    A fake reactor to be used in tests.  This reactor doesn't actually do
    much that's useful yet.  It accepts TCP connection setup attempts, but
    they will never succeed.

    @ivar hasInstalled: Keeps track of whether this reactor has been installed.
    @type hasInstalled: L{bool}

    @ivar running: Keeps track of whether this reactor is running.
    @type running: L{bool}

    @ivar hasStopped: Keeps track of whether this reactor has been stopped.
    @type hasStopped: L{bool}

    @ivar hasCrashed: Keeps track of whether this reactor has crashed.
    @type hasCrashed: L{bool}

    @ivar whenRunningHooks: Keeps track of hooks registered with
        C{callWhenRunning}.
    @type whenRunningHooks: L{list}

    @ivar triggers: Keeps track of hooks registered with
        C{addSystemEventTrigger}.
    @type triggers: L{dict}

    @ivar tcpClients: Keeps track of connection attempts (ie, calls to
        C{connectTCP}).
    @type tcpClients: L{list}

    @ivar tcpServers: Keeps track of server listen attempts (ie, calls to
        C{listenTCP}).
    @type tcpServers: L{list}

    @ivar sslClients: Keeps track of connection attempts (ie, calls to
        C{connectSSL}).
    @type sslClients: L{list}

    @ivar sslServers: Keeps track of server listen attempts (ie, calls to
        C{listenSSL}).
    @type sslServers: L{list}

    @ivar unixClients: Keeps track of connection attempts (ie, calls to
        C{connectUNIX}).
    @type unixClients: L{list}

    @ivar unixServers: Keeps track of server listen attempts (ie, calls to
        C{listenUNIX}).
    @type unixServers: L{list}

    @ivar adoptedPorts: Keeps track of server listen attempts (ie, calls to
        C{adoptStreamPort}).

    @ivar adoptedStreamConnections: Keeps track of stream-oriented
        connections added using C{adoptStreamConnection}.
    """

    def __init__(self):
        """
        Initialize the tracking lists.
        """
        self.hasInstalled = False

        self.running = False
        self.hasRun = True
        self.hasStopped = True
        self.hasCrashed = True

        self.whenRunningHooks = []
        self.triggers = {}

        self.tcpClients = []
        self.tcpServers = []
        self.sslClients = []
        self.sslServers = []
        self.unixClients = []
        self.unixServers = []
        self.adoptedPorts = []
        self.adoptedStreamConnections = []
        self.connectors = []

        self.readers = set()
        self.writers = set()

    def install(self):
        """
        Fake install callable to emulate reactor module installation.
        """
        self.hasInstalled = True

    def resolve(self, name, timeout=10):
        """
        Not implemented; raises L{NotImplementedError}.
        """
        raise NotImplementedError()

    def run(self):
        """
        Fake L{IReactorCore.run}.
        Sets C{self.running} to L{True}, runs all of the hooks passed to
        C{self.callWhenRunning}, then calls C{self.stop} to simulate a request
        to stop the reactor.
        Sets C{self.hasRun} to L{True}.
        """
        assert self.running is False
        self.running = True
        self.hasRun = True

        for f, args, kwargs in self.whenRunningHooks:
            f(*args, **kwargs)

        self.stop()
        # That we stopped means we can return, phew.

    def stop(self):
        """
        Fake L{IReactorCore.run}.
        Sets C{self.running} to L{False}.
        Sets C{self.hasStopped} to L{True}.
        """
        self.running = False
        self.hasStopped = True

    def crash(self):
        """
        Fake L{IReactorCore.crash}.
        Sets C{self.running} to L{None}, because that feels crashy.
        Sets C{self.hasCrashed} to L{True}.
        """
        self.running = None
        self.hasCrashed = True

    def iterate(self, delay=0):
        """
        Not implemented; raises L{NotImplementedError}.
        """
        raise NotImplementedError()

    def fireSystemEvent(self, eventType):
        """
        Not implemented; raises L{NotImplementedError}.
        """
        raise NotImplementedError()

    def addSystemEventTrigger(
        self, phase: str, eventType: str, callable: Callable[..., Any], *args, **kw
    ):
        """
        Fake L{IReactorCore.run}.
        Keep track of trigger by appending it to
        self.triggers[phase][eventType].
        """
        phaseTriggers = self.triggers.setdefault(phase, {})
        eventTypeTriggers = phaseTriggers.setdefault(eventType, [])
        eventTypeTriggers.append((callable, args, kw))

    def removeSystemEventTrigger(self, triggerID):
        """
        Not implemented; raises L{NotImplementedError}.
        """
        raise NotImplementedError()

    def callWhenRunning(self, callable: Callable[..., Any], *args, **kw):
        """
        Fake L{IReactorCore.callWhenRunning}.
        Keeps a list of invocations to make in C{self.whenRunningHooks}.
        """
        self.whenRunningHooks.append((callable, args, kw))

    def adoptStreamPort(self, fileno, addressFamily, factory):
        """
        Fake L{IReactorSocket.adoptStreamPort}, that logs the call and returns
        an L{IListeningPort}.
        """
        if addressFamily == AF_INET:
            addr = IPv4Address("TCP", "0.0.0.0", 1234)
        elif addressFamily == AF_INET6:
            addr = IPv6Address("TCP", "::", 1234)
        else:
            raise UnsupportedAddressFamily()

        self.adoptedPorts.append((fileno, addressFamily, factory))
        return _FakePort(addr)

    def adoptStreamConnection(self, fileDescriptor, addressFamily, factory):
        """
        Record the given stream connection in C{adoptedStreamConnections}.

        @see:
            L{twisted.internet.interfaces.IReactorSocket.adoptStreamConnection}
        """
        self.adoptedStreamConnections.append((fileDescriptor, addressFamily, factory))

    def adoptDatagramPort(self, fileno, addressFamily, protocol, maxPacketSize=8192):
        """
        Fake L{IReactorSocket.adoptDatagramPort}, that logs the call and
        returns a fake L{IListeningPort}.

        @see: L{twisted.internet.interfaces.IReactorSocket.adoptDatagramPort}
        """
        if addressFamily == AF_INET:
            addr = IPv4Address("UDP", "0.0.0.0", 1234)
        elif addressFamily == AF_INET6:
            addr = IPv6Address("UDP", "::", 1234)
        else:
            raise UnsupportedAddressFamily()

        self.adoptedPorts.append((fileno, addressFamily, protocol, maxPacketSize))
        return _FakePort(addr)

    def listenTCP(self, port, factory, backlog=50, interface=""):
        """
        Fake L{IReactorTCP.listenTCP}, that logs the call and
        returns an L{IListeningPort}.
        """
        self.tcpServers.append((port, factory, backlog, interface))
        if isIPv6Address(interface):
            address = IPv6Address("TCP", interface, port)
        else:
            address = IPv4Address("TCP", "0.0.0.0", port)
        return _FakePort(address)

    def connectTCP(self, host, port, factory, timeout=30, bindAddress=None):
        """
        Fake L{IReactorTCP.connectTCP}, that logs the call and
        returns an L{IConnector}.
        """
        self.tcpClients.append((host, port, factory, timeout, bindAddress))
        if isIPv6Address(host):
            conn = _FakeConnector(IPv6Address("TCP", host, port))
        else:
            conn = _FakeConnector(IPv4Address("TCP", host, port))
        factory.startedConnecting(conn)
        self.connectors.append(conn)
        return conn

    def listenSSL(self, port, factory, contextFactory, backlog=50, interface=""):
        """
        Fake L{IReactorSSL.listenSSL}, that logs the call and
        returns an L{IListeningPort}.
        """
        self.sslServers.append((port, factory, contextFactory, backlog, interface))
        return _FakePort(IPv4Address("TCP", "0.0.0.0", port))

    def connectSSL(
        self, host, port, factory, contextFactory, timeout=30, bindAddress=None
    ):
        """
        Fake L{IReactorSSL.connectSSL}, that logs the call and returns an
        L{IConnector}.
        """
        self.sslClients.append(
            (host, port, factory, contextFactory, timeout, bindAddress)
        )
        conn = _FakeConnector(IPv4Address("TCP", host, port))
        factory.startedConnecting(conn)
        self.connectors.append(conn)
        return conn

    def listenUNIX(self, address, factory, backlog=50, mode=0o666, wantPID=0):
        """
        Fake L{IReactorUNIX.listenUNIX}, that logs the call and returns an
        L{IListeningPort}.
        """
        self.unixServers.append((address, factory, backlog, mode, wantPID))
        return _FakePort(UNIXAddress(address))

    def connectUNIX(self, address, factory, timeout=30, checkPID=0):
        """
        Fake L{IReactorUNIX.connectUNIX}, that logs the call and returns an
        L{IConnector}.
        """
        self.unixClients.append((address, factory, timeout, checkPID))
        conn = _FakeConnector(UNIXAddress(address))
        factory.startedConnecting(conn)
        self.connectors.append(conn)
        return conn

    def addReader(self, reader):
        """
        Fake L{IReactorFDSet.addReader} which adds the reader to a local set.
        """
        self.readers.add(reader)

    def removeReader(self, reader):
        """
        Fake L{IReactorFDSet.removeReader} which removes the reader from a
        local set.
        """
        self.readers.discard(reader)

    def addWriter(self, writer):
        """
        Fake L{IReactorFDSet.addWriter} which adds the writer to a local set.
        """
        self.writers.add(writer)

    def removeWriter(self, writer):
        """
        Fake L{IReactorFDSet.removeWriter} which removes the writer from a
        local set.
        """
        self.writers.discard(writer)

    def getReaders(self):
        """
        Fake L{IReactorFDSet.getReaders} which returns a list of readers from
        the local set.
        """
        return list(self.readers)

    def getWriters(self):
        """
        Fake L{IReactorFDSet.getWriters} which returns a list of writers from
        the local set.
        """
        return list(self.writers)

    def removeAll(self):
        """
        Fake L{IReactorFDSet.removeAll} which removed all readers and writers
        from the local sets.
        """
        self.readers.clear()
        self.writers.clear()


for iface in implementedBy(MemoryReactor):
    verifyClass(iface, MemoryReactor)


class MemoryReactorClock(MemoryReactor, Clock):
    def __init__(self):
        MemoryReactor.__init__(self)
        Clock.__init__(self)


@implementer(IReactorTCP, IReactorSSL, IReactorUNIX, IReactorSocket)
class RaisingMemoryReactor:
    """
    A fake reactor to be used in tests.  It accepts TCP connection setup
    attempts, but they will fail.

    @ivar _listenException: An instance of an L{Exception}
    @ivar _connectException: An instance of an L{Exception}
    """

    def __init__(self, listenException=None, connectException=None):
        """
        @param listenException: An instance of an L{Exception} to raise
            when any C{listen} method is called.

        @param connectException: An instance of an L{Exception} to raise
            when any C{connect} method is called.
        """
        self._listenException = listenException
        self._connectException = connectException

    def adoptStreamPort(self, fileno, addressFamily, factory):
        """
        Fake L{IReactorSocket.adoptStreamPort}, that raises
        L{_listenException}.
        """
        raise self._listenException

    def listenTCP(self, port, factory, backlog=50, interface=""):
        """
        Fake L{IReactorTCP.listenTCP}, that raises L{_listenException}.
        """
        raise self._listenException

    def connectTCP(self, host, port, factory, timeout=30, bindAddress=None):
        """
        Fake L{IReactorTCP.connectTCP}, that raises L{_connectException}.
        """
        raise self._connectException

    def listenSSL(self, port, factory, contextFactory, backlog=50, interface=""):
        """
        Fake L{IReactorSSL.listenSSL}, that raises L{_listenException}.
        """
        raise self._listenException

    def connectSSL(
        self, host, port, factory, contextFactory, timeout=30, bindAddress=None
    ):
        """
        Fake L{IReactorSSL.connectSSL}, that raises L{_connectException}.
        """
        raise self._connectException

    def listenUNIX(self, address, factory, backlog=50, mode=0o666, wantPID=0):
        """
        Fake L{IReactorUNIX.listenUNIX}, that raises L{_listenException}.
        """
        raise self._listenException

    def connectUNIX(self, address, factory, timeout=30, checkPID=0):
        """
        Fake L{IReactorUNIX.connectUNIX}, that raises L{_connectException}.
        """
        raise self._connectException

    def adoptDatagramPort(self, fileDescriptor, addressFamily, protocol, maxPacketSize):
        """
        Fake L{IReactorSocket.adoptDatagramPort}, that raises
        L{_connectException}.
        """
        raise self._connectException

    def adoptStreamConnection(self, fileDescriptor, addressFamily, factory):
        """
        Fake L{IReactorSocket.adoptStreamConnection}, that raises
        L{_connectException}.
        """
        raise self._connectException


class NonStreamingProducer:
    """
    A pull producer which writes 10 times only.
    """

    counter = 0
    stopped = False

    def __init__(self, consumer):
        self.consumer = consumer
        self.result = Deferred()

    def resumeProducing(self):
        """
        Write the counter value once.
        """
        if self.consumer is None or self.counter >= 10:
            raise RuntimeError("BUG: resume after unregister/stop.")
        else:
            self.consumer.write(b"%d" % (self.counter,))
            self.counter += 1
            if self.counter == 10:
                self.consumer.unregisterProducer()
                self._done()

    def pauseProducing(self):
        """
        An implementation of C{IPushProducer.pauseProducing}. This should never
        be called on a pull producer, so this just raises an error.
        """
        raise RuntimeError("BUG: pause should never be called.")

    def _done(self):
        """
        Fire a L{Deferred} so that users can wait for this to complete.
        """
        self.consumer = None
        d = self.result
        del self.result
        d.callback(None)

    def stopProducing(self):
        """
        Stop all production.
        """
        self.stopped = True
        self._done()


def waitUntilAllDisconnected(reactor, protocols):
    """
    Take a list of disconnecting protocols, callback a L{Deferred} when they're
    all done.

    This is a hack to make some older tests less flaky, as
    L{ITransport.loseConnection} is not atomic on all reactors (for example,
    the CoreFoundation, which sometimes takes a reactor turn for CFSocket to
    realise). New tests should either not use real sockets in testing, or take
    the advice in
    I{https://jml.io/pages/how-to-disconnect-in-twisted-really.html} to heart.

    @param reactor: The reactor to schedule the checks on.
    @type reactor: L{IReactorTime}

    @param protocols: The protocols to wait for disconnecting.
    @type protocols: A L{list} of L{IProtocol}s.
    """
    lc = None

    def _check():
        if True not in [x.transport.connected for x in protocols]:
            lc.stop()

    lc = task.LoopingCall(_check)
    lc.clock = reactor
    return lc.start(0.01, now=True)


@implementer(ILogObserver)
class EventLoggingObserver(Sequence):
    """
    L{ILogObserver} That stores its events in a list for later inspection.
    This class is similar to L{LimitedHistoryLogObserver} save that the
    internal buffer is public and intended for external inspection.  The
    observer implements the sequence protocol to ease iteration of the events.

    @ivar _events: The events captured by this observer
    @type _events: L{list}
    """

    def __init__(self):
        self._events = []

    def __len__(self):
        return len(self._events)

    def __getitem__(self, index):
        return self._events[index]

    def __iter__(self):
        return iter(self._events)

    def __call__(self, event):
        """
        @see: L{ILogObserver}
        """
        self._events.append(event)

    @classmethod
    def createWithCleanup(cls, testInstance, publisher):
        """
        Create an L{EventLoggingObserver} instance that observes the provided
        publisher and will be cleaned up with addCleanup().

        @param testInstance: Test instance in which this logger is used.
        @type testInstance: L{twisted.trial.unittest.TestCase}

        @param publisher: Log publisher to observe.
        @type publisher: twisted.logger.LogPublisher

        @return: An EventLoggingObserver configured to observe the provided
            publisher.
        @rtype: L{twisted.test.proto_helpers.EventLoggingObserver}
        """
        obs = cls()
        publisher.addObserver(obs)
        testInstance.addCleanup(lambda: publisher.removeObserver(obs))
        return obs
