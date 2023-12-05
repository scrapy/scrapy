# -*- test-case-name: twisted.test.test_stdio -*-

"""Standard input/out/err support.

Future Plans::

    support for stderr, perhaps
    Rewrite to use the reactor instead of an ad-hoc mechanism for connecting
        protocols to transport.

Maintainer: James Y Knight
"""

from zope.interface import implementer

from twisted.internet import error, interfaces, process
from twisted.python import failure, log


@implementer(interfaces.IAddress)
class PipeAddress:
    pass


@implementer(
    interfaces.ITransport,
    interfaces.IProducer,
    interfaces.IConsumer,
    interfaces.IHalfCloseableDescriptor,
)
class StandardIO:

    _reader = None
    _writer = None
    disconnected = False
    disconnecting = False

    def __init__(self, proto, stdin=0, stdout=1, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self.protocol = proto

        self._writer = process.ProcessWriter(reactor, self, "write", stdout)
        self._reader = process.ProcessReader(reactor, self, "read", stdin)
        self._reader.startReading()
        self.protocol.makeConnection(self)

    # ITransport

    # XXX Actually, see #3597.
    def loseWriteConnection(self):
        if self._writer is not None:
            self._writer.loseConnection()

    def write(self, data):
        if self._writer is not None:
            self._writer.write(data)

    def writeSequence(self, data):
        if self._writer is not None:
            self._writer.writeSequence(data)

    def loseConnection(self):
        self.disconnecting = True

        if self._writer is not None:
            self._writer.loseConnection()
        if self._reader is not None:
            # Don't loseConnection, because we don't want to SIGPIPE it.
            self._reader.stopReading()

    def getPeer(self):
        return PipeAddress()

    def getHost(self):
        return PipeAddress()

    # Callbacks from process.ProcessReader/ProcessWriter
    def childDataReceived(self, fd, data):
        self.protocol.dataReceived(data)

    def childConnectionLost(self, fd, reason):
        if self.disconnected:
            return

        if reason.value.__class__ == error.ConnectionDone:
            # Normal close
            if fd == "read":
                self._readConnectionLost(reason)
            else:
                self._writeConnectionLost(reason)
        else:
            self.connectionLost(reason)

    def connectionLost(self, reason):
        self.disconnected = True

        # Make sure to cleanup the other half
        _reader = self._reader
        _writer = self._writer
        protocol = self.protocol
        self._reader = self._writer = None
        self.protocol = None

        if _writer is not None and not _writer.disconnected:
            _writer.connectionLost(reason)

        if _reader is not None and not _reader.disconnected:
            _reader.connectionLost(reason)

        try:
            protocol.connectionLost(reason)
        except BaseException:
            log.err()

    def _writeConnectionLost(self, reason):
        self._writer = None
        if self.disconnecting:
            self.connectionLost(reason)
            return

        p = interfaces.IHalfCloseableProtocol(self.protocol, None)
        if p:
            try:
                p.writeConnectionLost()
            except BaseException:
                log.err()
                self.connectionLost(failure.Failure())

    def _readConnectionLost(self, reason):
        self._reader = None
        p = interfaces.IHalfCloseableProtocol(self.protocol, None)
        if p:
            try:
                p.readConnectionLost()
            except BaseException:
                log.err()
                self.connectionLost(failure.Failure())
        else:
            self.connectionLost(reason)

    # IConsumer
    def registerProducer(self, producer, streaming):
        if self._writer is None:
            producer.stopProducing()
        else:
            self._writer.registerProducer(producer, streaming)

    def unregisterProducer(self):
        if self._writer is not None:
            self._writer.unregisterProducer()

    # IProducer
    def stopProducing(self):
        self.loseConnection()

    def pauseProducing(self):
        if self._reader is not None:
            self._reader.pauseProducing()

    def resumeProducing(self):
        if self._reader is not None:
            self._reader.resumeProducing()

    def stopReading(self):
        """Compatibility only, don't use. Call pauseProducing."""
        self.pauseProducing()

    def startReading(self):
        """Compatibility only, don't use. Call resumeProducing."""
        self.resumeProducing()

    def readConnectionLost(self, reason):
        # L{IHalfCloseableDescriptor.readConnectionLost}
        raise NotImplementedError()

    def writeConnectionLost(self, reason):
        # L{IHalfCloseableDescriptor.writeConnectionLost}
        raise NotImplementedError()
