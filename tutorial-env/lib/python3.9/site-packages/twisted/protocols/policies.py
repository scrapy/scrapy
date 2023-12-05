# -*- test-case-name: twisted.test.test_policies -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Resource limiting policies.

@seealso: See also L{twisted.protocols.htb} for rate limiting.
"""


# system imports
import sys
from typing import Optional, Type

from zope.interface import directlyProvides, providedBy

from twisted.internet import error, interfaces
from twisted.internet.interfaces import ILoggingContext

# twisted imports
from twisted.internet.protocol import ClientFactory, Protocol, ServerFactory
from twisted.python import log


def _wrappedLogPrefix(wrapper, wrapped):
    """
    Compute a log prefix for a wrapper and the object it wraps.

    @rtype: C{str}
    """
    if ILoggingContext.providedBy(wrapped):
        logPrefix = wrapped.logPrefix()
    else:
        logPrefix = wrapped.__class__.__name__
    return f"{logPrefix} ({wrapper.__class__.__name__})"


class ProtocolWrapper(Protocol):
    """
    Wraps protocol instances and acts as their transport as well.

    @ivar wrappedProtocol: An L{IProtocol<twisted.internet.interfaces.IProtocol>}
        provider to which L{IProtocol<twisted.internet.interfaces.IProtocol>}
        method calls onto this L{ProtocolWrapper} will be proxied.

    @ivar factory: The L{WrappingFactory} which created this
        L{ProtocolWrapper}.
    """

    disconnecting = 0

    def __init__(
        self, factory: "WrappingFactory", wrappedProtocol: interfaces.IProtocol
    ):
        self.wrappedProtocol = wrappedProtocol
        self.factory = factory

    def logPrefix(self):
        """
        Use a customized log prefix mentioning both the wrapped protocol and
        the current one.
        """
        return _wrappedLogPrefix(self, self.wrappedProtocol)

    def makeConnection(self, transport):
        """
        When a connection is made, register this wrapper with its factory,
        save the real transport, and connect the wrapped protocol to this
        L{ProtocolWrapper} to intercept any transport calls it makes.
        """
        directlyProvides(self, providedBy(transport))
        Protocol.makeConnection(self, transport)
        self.factory.registerProtocol(self)
        self.wrappedProtocol.makeConnection(self)

    # Transport relaying

    def write(self, data):
        self.transport.write(data)

    def writeSequence(self, data):
        self.transport.writeSequence(data)

    def loseConnection(self):
        self.disconnecting = 1
        self.transport.loseConnection()

    def getPeer(self):
        return self.transport.getPeer()

    def getHost(self):
        return self.transport.getHost()

    def registerProducer(self, producer, streaming):
        self.transport.registerProducer(producer, streaming)

    def unregisterProducer(self):
        self.transport.unregisterProducer()

    def stopConsuming(self):
        self.transport.stopConsuming()

    def __getattr__(self, name):
        return getattr(self.transport, name)

    # Protocol relaying

    def dataReceived(self, data):
        self.wrappedProtocol.dataReceived(data)

    def connectionLost(self, reason):
        self.factory.unregisterProtocol(self)
        self.wrappedProtocol.connectionLost(reason)

        # Breaking reference cycle between self and wrappedProtocol.
        self.wrappedProtocol = None


class WrappingFactory(ClientFactory):
    """
    Wraps a factory and its protocols, and keeps track of them.
    """

    protocol: Type[Protocol] = ProtocolWrapper

    def __init__(self, wrappedFactory):
        self.wrappedFactory = wrappedFactory
        self.protocols = {}

    def logPrefix(self):
        """
        Generate a log prefix mentioning both the wrapped factory and this one.
        """
        return _wrappedLogPrefix(self, self.wrappedFactory)

    def doStart(self):
        self.wrappedFactory.doStart()
        ClientFactory.doStart(self)

    def doStop(self):
        self.wrappedFactory.doStop()
        ClientFactory.doStop(self)

    def startedConnecting(self, connector):
        self.wrappedFactory.startedConnecting(connector)

    def clientConnectionFailed(self, connector, reason):
        self.wrappedFactory.clientConnectionFailed(connector, reason)

    def clientConnectionLost(self, connector, reason):
        self.wrappedFactory.clientConnectionLost(connector, reason)

    def buildProtocol(self, addr):
        return self.protocol(self, self.wrappedFactory.buildProtocol(addr))

    def registerProtocol(self, p):
        """
        Called by protocol to register itself.
        """
        self.protocols[p] = 1

    def unregisterProtocol(self, p):
        """
        Called by protocols when they go away.
        """
        del self.protocols[p]


class ThrottlingProtocol(ProtocolWrapper):
    """
    Protocol for L{ThrottlingFactory}.
    """

    # wrap API for tracking bandwidth

    def write(self, data):
        self.factory.registerWritten(len(data))
        ProtocolWrapper.write(self, data)

    def writeSequence(self, seq):
        self.factory.registerWritten(sum(map(len, seq)))
        ProtocolWrapper.writeSequence(self, seq)

    def dataReceived(self, data):
        self.factory.registerRead(len(data))
        ProtocolWrapper.dataReceived(self, data)

    def registerProducer(self, producer, streaming):
        self.producer = producer
        ProtocolWrapper.registerProducer(self, producer, streaming)

    def unregisterProducer(self):
        del self.producer
        ProtocolWrapper.unregisterProducer(self)

    def throttleReads(self):
        self.transport.pauseProducing()

    def unthrottleReads(self):
        self.transport.resumeProducing()

    def throttleWrites(self):
        if hasattr(self, "producer"):
            self.producer.pauseProducing()

    def unthrottleWrites(self):
        if hasattr(self, "producer"):
            self.producer.resumeProducing()


class ThrottlingFactory(WrappingFactory):
    """
    Throttles bandwidth and number of connections.

    Write bandwidth will only be throttled if there is a producer
    registered.
    """

    protocol = ThrottlingProtocol

    def __init__(
        self,
        wrappedFactory,
        maxConnectionCount=sys.maxsize,
        readLimit=None,
        writeLimit=None,
    ):
        WrappingFactory.__init__(self, wrappedFactory)
        self.connectionCount = 0
        self.maxConnectionCount = maxConnectionCount
        self.readLimit = readLimit  # max bytes we should read per second
        self.writeLimit = writeLimit  # max bytes we should write per second
        self.readThisSecond = 0
        self.writtenThisSecond = 0
        self.unthrottleReadsID = None
        self.checkReadBandwidthID = None
        self.unthrottleWritesID = None
        self.checkWriteBandwidthID = None

    def callLater(self, period, func):
        """
        Wrapper around
        L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}
        for test purpose.
        """
        from twisted.internet import reactor

        return reactor.callLater(period, func)

    def registerWritten(self, length):
        """
        Called by protocol to tell us more bytes were written.
        """
        self.writtenThisSecond += length

    def registerRead(self, length):
        """
        Called by protocol to tell us more bytes were read.
        """
        self.readThisSecond += length

    def checkReadBandwidth(self):
        """
        Checks if we've passed bandwidth limits.
        """
        if self.readThisSecond > self.readLimit:
            self.throttleReads()
            throttleTime = (float(self.readThisSecond) / self.readLimit) - 1.0
            self.unthrottleReadsID = self.callLater(throttleTime, self.unthrottleReads)
        self.readThisSecond = 0
        self.checkReadBandwidthID = self.callLater(1, self.checkReadBandwidth)

    def checkWriteBandwidth(self):
        if self.writtenThisSecond > self.writeLimit:
            self.throttleWrites()
            throttleTime = (float(self.writtenThisSecond) / self.writeLimit) - 1.0
            self.unthrottleWritesID = self.callLater(
                throttleTime, self.unthrottleWrites
            )
        # reset for next round
        self.writtenThisSecond = 0
        self.checkWriteBandwidthID = self.callLater(1, self.checkWriteBandwidth)

    def throttleReads(self):
        """
        Throttle reads on all protocols.
        """
        log.msg("Throttling reads on %s" % self)
        for p in self.protocols.keys():
            p.throttleReads()

    def unthrottleReads(self):
        """
        Stop throttling reads on all protocols.
        """
        self.unthrottleReadsID = None
        log.msg("Stopped throttling reads on %s" % self)
        for p in self.protocols.keys():
            p.unthrottleReads()

    def throttleWrites(self):
        """
        Throttle writes on all protocols.
        """
        log.msg("Throttling writes on %s" % self)
        for p in self.protocols.keys():
            p.throttleWrites()

    def unthrottleWrites(self):
        """
        Stop throttling writes on all protocols.
        """
        self.unthrottleWritesID = None
        log.msg("Stopped throttling writes on %s" % self)
        for p in self.protocols.keys():
            p.unthrottleWrites()

    def buildProtocol(self, addr):
        if self.connectionCount == 0:
            if self.readLimit is not None:
                self.checkReadBandwidth()
            if self.writeLimit is not None:
                self.checkWriteBandwidth()

        if self.connectionCount < self.maxConnectionCount:
            self.connectionCount += 1
            return WrappingFactory.buildProtocol(self, addr)
        else:
            log.msg("Max connection count reached!")
            return None

    def unregisterProtocol(self, p):
        WrappingFactory.unregisterProtocol(self, p)
        self.connectionCount -= 1
        if self.connectionCount == 0:
            if self.unthrottleReadsID is not None:
                self.unthrottleReadsID.cancel()
            if self.checkReadBandwidthID is not None:
                self.checkReadBandwidthID.cancel()
            if self.unthrottleWritesID is not None:
                self.unthrottleWritesID.cancel()
            if self.checkWriteBandwidthID is not None:
                self.checkWriteBandwidthID.cancel()


class SpewingProtocol(ProtocolWrapper):
    def dataReceived(self, data):
        log.msg("Received: %r" % data)
        ProtocolWrapper.dataReceived(self, data)

    def write(self, data):
        log.msg("Sending: %r" % data)
        ProtocolWrapper.write(self, data)


class SpewingFactory(WrappingFactory):
    protocol = SpewingProtocol


class LimitConnectionsByPeer(WrappingFactory):

    maxConnectionsPerPeer = 5

    def startFactory(self):
        self.peerConnections = {}

    def buildProtocol(self, addr):
        peerHost = addr[0]
        connectionCount = self.peerConnections.get(peerHost, 0)
        if connectionCount >= self.maxConnectionsPerPeer:
            return None
        self.peerConnections[peerHost] = connectionCount + 1
        return WrappingFactory.buildProtocol(self, addr)

    def unregisterProtocol(self, p):
        peerHost = p.getPeer()[1]
        self.peerConnections[peerHost] -= 1
        if self.peerConnections[peerHost] == 0:
            del self.peerConnections[peerHost]


class LimitTotalConnectionsFactory(ServerFactory):
    """
    Factory that limits the number of simultaneous connections.

    @type connectionCount: C{int}
    @ivar connectionCount: number of current connections.
    @type connectionLimit: C{int} or L{None}
    @cvar connectionLimit: maximum number of connections.
    @type overflowProtocol: L{Protocol} or L{None}
    @cvar overflowProtocol: Protocol to use for new connections when
        connectionLimit is exceeded.  If L{None} (the default value), excess
        connections will be closed immediately.
    """

    connectionCount = 0
    connectionLimit = None
    overflowProtocol: Optional[Type[Protocol]] = None

    def buildProtocol(self, addr):
        if self.connectionLimit is None or self.connectionCount < self.connectionLimit:
            # Build the normal protocol
            wrappedProtocol = self.protocol()
        elif self.overflowProtocol is None:
            # Just drop the connection
            return None
        else:
            # Too many connections, so build the overflow protocol
            wrappedProtocol = self.overflowProtocol()

        wrappedProtocol.factory = self
        protocol = ProtocolWrapper(self, wrappedProtocol)
        self.connectionCount += 1
        return protocol

    def registerProtocol(self, p):
        pass

    def unregisterProtocol(self, p):
        self.connectionCount -= 1


class TimeoutProtocol(ProtocolWrapper):
    """
    Protocol that automatically disconnects when the connection is idle.
    """

    def __init__(self, factory, wrappedProtocol, timeoutPeriod):
        """
        Constructor.

        @param factory: An L{TimeoutFactory}.
        @param wrappedProtocol: A L{Protocol} to wrapp.
        @param timeoutPeriod: Number of seconds to wait for activity before
            timing out.
        """
        ProtocolWrapper.__init__(self, factory, wrappedProtocol)
        self.timeoutCall = None
        self.timeoutPeriod = None
        self.setTimeout(timeoutPeriod)

    def setTimeout(self, timeoutPeriod=None):
        """
        Set a timeout.

        This will cancel any existing timeouts.

        @param timeoutPeriod: If not L{None}, change the timeout period.
            Otherwise, use the existing value.
        """
        self.cancelTimeout()
        self.timeoutPeriod = timeoutPeriod
        if timeoutPeriod is not None:
            self.timeoutCall = self.factory.callLater(
                self.timeoutPeriod, self.timeoutFunc
            )

    def cancelTimeout(self):
        """
        Cancel the timeout.

        If the timeout was already cancelled, this does nothing.
        """
        self.timeoutPeriod = None
        if self.timeoutCall:
            try:
                self.timeoutCall.cancel()
            except (error.AlreadyCalled, error.AlreadyCancelled):
                pass
            self.timeoutCall = None

    def resetTimeout(self):
        """
        Reset the timeout, usually because some activity just happened.
        """
        if self.timeoutCall:
            self.timeoutCall.reset(self.timeoutPeriod)

    def write(self, data):
        self.resetTimeout()
        ProtocolWrapper.write(self, data)

    def writeSequence(self, seq):
        self.resetTimeout()
        ProtocolWrapper.writeSequence(self, seq)

    def dataReceived(self, data):
        self.resetTimeout()
        ProtocolWrapper.dataReceived(self, data)

    def connectionLost(self, reason):
        self.cancelTimeout()
        ProtocolWrapper.connectionLost(self, reason)

    def timeoutFunc(self):
        """
        This method is called when the timeout is triggered.

        By default it calls I{loseConnection}.  Override this if you want
        something else to happen.
        """
        self.loseConnection()


class TimeoutFactory(WrappingFactory):
    """
    Factory for TimeoutWrapper.
    """

    protocol = TimeoutProtocol

    def __init__(self, wrappedFactory, timeoutPeriod=30 * 60):
        self.timeoutPeriod = timeoutPeriod
        WrappingFactory.__init__(self, wrappedFactory)

    def buildProtocol(self, addr):
        return self.protocol(
            self,
            self.wrappedFactory.buildProtocol(addr),
            timeoutPeriod=self.timeoutPeriod,
        )

    def callLater(self, period, func):
        """
        Wrapper around
        L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}
        for test purpose.
        """
        from twisted.internet import reactor

        return reactor.callLater(period, func)


class TrafficLoggingProtocol(ProtocolWrapper):
    def __init__(self, factory, wrappedProtocol, logfile, lengthLimit=None, number=0):
        """
        @param factory: factory which created this protocol.
        @type factory: L{protocol.Factory}.
        @param wrappedProtocol: the underlying protocol.
        @type wrappedProtocol: C{protocol.Protocol}.
        @param logfile: file opened for writing used to write log messages.
        @type logfile: C{file}
        @param lengthLimit: maximum size of the datareceived logged.
        @type lengthLimit: C{int}
        @param number: identifier of the connection.
        @type number: C{int}.
        """
        ProtocolWrapper.__init__(self, factory, wrappedProtocol)
        self.logfile = logfile
        self.lengthLimit = lengthLimit
        self._number = number

    def _log(self, line):
        self.logfile.write(line + "\n")
        self.logfile.flush()

    def _mungeData(self, data):
        if self.lengthLimit and len(data) > self.lengthLimit:
            data = data[: self.lengthLimit - 12] + "<... elided>"
        return data

    # IProtocol
    def connectionMade(self):
        self._log("*")
        return ProtocolWrapper.connectionMade(self)

    def dataReceived(self, data):
        self._log("C %d: %r" % (self._number, self._mungeData(data)))
        return ProtocolWrapper.dataReceived(self, data)

    def connectionLost(self, reason):
        self._log("C %d: %r" % (self._number, reason))
        return ProtocolWrapper.connectionLost(self, reason)

    # ITransport
    def write(self, data):
        self._log("S %d: %r" % (self._number, self._mungeData(data)))
        return ProtocolWrapper.write(self, data)

    def writeSequence(self, iovec):
        self._log("SV %d: %r" % (self._number, [self._mungeData(d) for d in iovec]))
        return ProtocolWrapper.writeSequence(self, iovec)

    def loseConnection(self):
        self._log("S %d: *" % (self._number,))
        return ProtocolWrapper.loseConnection(self)


class TrafficLoggingFactory(WrappingFactory):
    protocol = TrafficLoggingProtocol

    _counter = 0

    def __init__(self, wrappedFactory, logfilePrefix, lengthLimit=None):
        self.logfilePrefix = logfilePrefix
        self.lengthLimit = lengthLimit
        WrappingFactory.__init__(self, wrappedFactory)

    def open(self, name):
        return open(name, "w")

    def buildProtocol(self, addr):
        self._counter += 1
        logfile = self.open(self.logfilePrefix + "-" + str(self._counter))
        return self.protocol(
            self,
            self.wrappedFactory.buildProtocol(addr),
            logfile,
            self.lengthLimit,
            self._counter,
        )

    def resetCounter(self):
        """
        Reset the value of the counter used to identify connections.
        """
        self._counter = 0


class TimeoutMixin:
    """
    Mixin for protocols which wish to timeout connections.

    Protocols that mix this in have a single timeout, set using L{setTimeout}.
    When the timeout is hit, L{timeoutConnection} is called, which, by
    default, closes the connection.

    @cvar timeOut: The number of seconds after which to timeout the connection.
    """

    timeOut: Optional[int] = None

    __timeoutCall = None

    def callLater(self, period, func):
        """
        Wrapper around
        L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}
        for test purpose.
        """
        from twisted.internet import reactor

        return reactor.callLater(period, func)

    def resetTimeout(self):
        """
        Reset the timeout count down.

        If the connection has already timed out, then do nothing.  If the
        timeout has been cancelled (probably using C{setTimeout(None)}), also
        do nothing.

        It's often a good idea to call this when the protocol has received
        some meaningful input from the other end of the connection.  "I've got
        some data, they're still there, reset the timeout".
        """
        if self.__timeoutCall is not None and self.timeOut is not None:
            self.__timeoutCall.reset(self.timeOut)

    def setTimeout(self, period):
        """
        Change the timeout period

        @type period: C{int} or L{None}
        @param period: The period, in seconds, to change the timeout to, or
        L{None} to disable the timeout.
        """
        prev = self.timeOut
        self.timeOut = period

        if self.__timeoutCall is not None:
            if period is None:
                try:
                    self.__timeoutCall.cancel()
                except (error.AlreadyCancelled, error.AlreadyCalled):
                    # Do nothing if the call was already consumed.
                    pass
                self.__timeoutCall = None
            else:
                self.__timeoutCall.reset(period)
        elif period is not None:
            self.__timeoutCall = self.callLater(period, self.__timedOut)

        return prev

    def __timedOut(self):
        self.__timeoutCall = None
        self.timeoutConnection()

    def timeoutConnection(self):
        """
        Called when the connection times out.

        Override to define behavior other than dropping the connection.
        """
        self.transport.loseConnection()
