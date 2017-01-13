# -*- test-case-name: twisted.test.test_abstract -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Support for generic select()able objects.
"""

from __future__ import division, absolute_import

from socket import AF_INET6, inet_pton, error

from zope.interface import implementer

# Twisted Imports
from twisted.python.compat import _PY3, unicode, lazyByteSlice
from twisted.python import reflect, failure
from twisted.internet import interfaces, main

if _PY3:
    def _concatenate(bObj, offset, bArray):
        # Python 3 lacks the buffer() builtin and the other primitives don't
        # help in this case.  Just do the copy.  Perhaps later these buffers can
        # be joined and FileDescriptor can use writev().  Or perhaps bytearrays
        # would help.
        return bObj[offset:] + b"".join(bArray)
else:
    def _concatenate(bObj, offset, bArray):
        # Avoid one extra string copy by using a buffer to limit what we include
        # in the result.
        return buffer(bObj, offset) + b"".join(bArray)


class _ConsumerMixin(object):
    """
    L{IConsumer} implementations can mix this in to get C{registerProducer} and
    C{unregisterProducer} methods which take care of keeping track of a
    producer's state.

    Subclasses must provide three attributes which L{_ConsumerMixin} will read
    but not write:

      - connected: A C{bool} which is C{True} as long as the consumer has
        someplace to send bytes (for example, a TCP connection), and then
        C{False} when it no longer does.

      - disconnecting: A C{bool} which is C{False} until something like
        L{ITransport.loseConnection} is called, indicating that the send buffer
        should be flushed and the connection lost afterwards.  Afterwards,
        C{True}.

      - disconnected: A C{bool} which is C{False} until the consumer no longer
        has a place to send bytes, then C{True}.

    Subclasses must also override the C{startWriting} method.

    @ivar producer: L{None} if no producer is registered, otherwise the
        registered producer.

    @ivar producerPaused: A flag indicating whether the producer is currently
        paused.
    @type producerPaused: L{bool}

    @ivar streamingProducer: A flag indicating whether the producer was
        registered as a streaming (ie push) producer or not (ie a pull
        producer).  This will determine whether the consumer may ever need to
        pause and resume it, or if it can merely call C{resumeProducing} on it
        when buffer space is available.
    @ivar streamingProducer: C{bool} or C{int}

    """
    producer = None
    producerPaused = False
    streamingProducer = False

    def startWriting(self):
        """
        Override in a subclass to cause the reactor to monitor this selectable
        for write events.  This will be called once in C{unregisterProducer} if
        C{loseConnection} has previously been called, so that the connection can
        actually close.
        """
        raise NotImplementedError("%r did not implement startWriting")


    def registerProducer(self, producer, streaming):
        """
        Register to receive data from a producer.

        This sets this selectable to be a consumer for a producer.  When this
        selectable runs out of data on a write() call, it will ask the producer
        to resumeProducing(). When the FileDescriptor's internal data buffer is
        filled, it will ask the producer to pauseProducing(). If the connection
        is lost, FileDescriptor calls producer's stopProducing() method.

        If streaming is true, the producer should provide the IPushProducer
        interface. Otherwise, it is assumed that producer provides the
        IPullProducer interface. In this case, the producer won't be asked to
        pauseProducing(), but it has to be careful to write() data only when its
        resumeProducing() method is called.
        """
        if self.producer is not None:
            raise RuntimeError(
                "Cannot register producer %s, because producer %s was never "
                "unregistered." % (producer, self.producer))
        if self.disconnected:
            producer.stopProducing()
        else:
            self.producer = producer
            self.streamingProducer = streaming
            if not streaming:
                producer.resumeProducing()


    def unregisterProducer(self):
        """
        Stop consuming data from a producer, without disconnecting.
        """
        self.producer = None
        if self.connected and self.disconnecting:
            self.startWriting()



@implementer(interfaces.ILoggingContext)
class _LogOwner(object):
    """
    Mixin to help implement L{interfaces.ILoggingContext} for transports which
    have a protocol, the log prefix of which should also appear in the
    transport's log prefix.
    """

    def _getLogPrefix(self, applicationObject):
        """
        Determine the log prefix to use for messages related to
        C{applicationObject}, which may or may not be an
        L{interfaces.ILoggingContext} provider.

        @return: A C{str} giving the log prefix to use.
        """
        if interfaces.ILoggingContext.providedBy(applicationObject):
            return applicationObject.logPrefix()
        return applicationObject.__class__.__name__


    def logPrefix(self):
        """
        Override this method to insert custom logging behavior.  Its
        return value will be inserted in front of every line.  It may
        be called more times than the number of output lines.
        """
        return "-"



@implementer(
    interfaces.IPushProducer, interfaces.IReadWriteDescriptor,
    interfaces.IConsumer, interfaces.ITransport,
    interfaces.IHalfCloseableDescriptor)
class FileDescriptor(_ConsumerMixin, _LogOwner):
    """
    An object which can be operated on by select().

    This is an abstract superclass of all objects which may be notified when
    they are readable or writable; e.g. they have a file-descriptor that is
    valid to be passed to select(2).
    """
    connected = 0
    disconnected = 0
    disconnecting = 0
    _writeDisconnecting = False
    _writeDisconnected = False
    dataBuffer = b""
    offset = 0

    SEND_LIMIT = 128*1024

    def __init__(self, reactor=None):
        """
        @param reactor: An L{IReactorFDSet} provider which this descriptor will
            use to get readable and writeable event notifications.  If no value
            is given, the global reactor will be used.
        """
        if not reactor:
            from twisted.internet import reactor
        self.reactor = reactor
        self._tempDataBuffer = [] # will be added to dataBuffer in doWrite
        self._tempDataLen = 0


    def connectionLost(self, reason):
        """The connection was lost.

        This is called when the connection on a selectable object has been
        lost.  It will be called whether the connection was closed explicitly,
        an exception occurred in an event handler, or the other end of the
        connection closed it first.

        Clean up state here, but make sure to call back up to FileDescriptor.
        """
        self.disconnected = 1
        self.connected = 0
        if self.producer is not None:
            self.producer.stopProducing()
            self.producer = None
        self.stopReading()
        self.stopWriting()


    def writeSomeData(self, data):
        """
        Write as much as possible of the given data, immediately.

        This is called to invoke the lower-level writing functionality, such
        as a socket's send() method, or a file's write(); this method
        returns an integer or an exception.  If an integer, it is the number
        of bytes written (possibly zero); if an exception, it indicates the
        connection was lost.
        """
        raise NotImplementedError("%s does not implement writeSomeData" %
                                  reflect.qual(self.__class__))


    def doRead(self):
        """
        Called when data is available for reading.

        Subclasses must override this method. The result will be interpreted
        in the same way as a result of doWrite().
        """
        raise NotImplementedError("%s does not implement doRead" %
                                  reflect.qual(self.__class__))

    def doWrite(self):
        """
        Called when data can be written.

        @return: L{None} on success, an exception or a negative integer on
            failure.

        @see: L{twisted.internet.interfaces.IWriteDescriptor.doWrite}.
        """
        if len(self.dataBuffer) - self.offset < self.SEND_LIMIT:
            # If there is currently less than SEND_LIMIT bytes left to send
            # in the string, extend it with the array data.
            self.dataBuffer = _concatenate(
                self.dataBuffer, self.offset, self._tempDataBuffer)
            self.offset = 0
            self._tempDataBuffer = []
            self._tempDataLen = 0

        # Send as much data as you can.
        if self.offset:
            l = self.writeSomeData(lazyByteSlice(self.dataBuffer, self.offset))
        else:
            l = self.writeSomeData(self.dataBuffer)

        # There is no writeSomeData implementation in Twisted which returns
        # < 0, but the documentation for writeSomeData used to claim negative
        # integers meant connection lost.  Keep supporting this here,
        # although it may be worth deprecating and removing at some point.
        if isinstance(l, Exception) or l < 0:
            return l
        self.offset += l
        # If there is nothing left to send,
        if self.offset == len(self.dataBuffer) and not self._tempDataLen:
            self.dataBuffer = b""
            self.offset = 0
            # stop writing.
            self.stopWriting()
            # If I've got a producer who is supposed to supply me with data,
            if self.producer is not None and ((not self.streamingProducer)
                                              or self.producerPaused):
                # tell them to supply some more.
                self.producerPaused = False
                self.producer.resumeProducing()
            elif self.disconnecting:
                # But if I was previously asked to let the connection die, do
                # so.
                return self._postLoseConnection()
            elif self._writeDisconnecting:
                # I was previously asked to half-close the connection.  We
                # set _writeDisconnected before calling handler, in case the
                # handler calls loseConnection(), which will want to check for
                # this attribute.
                self._writeDisconnected = True
                result = self._closeWriteConnection()
                return result
        return None

    def _postLoseConnection(self):
        """Called after a loseConnection(), when all data has been written.

        Whatever this returns is then returned by doWrite.
        """
        # default implementation, telling reactor we're finished
        return main.CONNECTION_DONE

    def _closeWriteConnection(self):
        # override in subclasses
        pass

    def writeConnectionLost(self, reason):
        # in current code should never be called
        self.connectionLost(reason)

    def readConnectionLost(self, reason):
        # override in subclasses
        self.connectionLost(reason)


    def _isSendBufferFull(self):
        """
        Determine whether the user-space send buffer for this transport is full
        or not.

        When the buffer contains more than C{self.bufferSize} bytes, it is
        considered full.  This might be improved by considering the size of the
        kernel send buffer and how much of it is free.

        @return: C{True} if it is full, C{False} otherwise.
        """
        return len(self.dataBuffer) + self._tempDataLen > self.bufferSize


    def _maybePauseProducer(self):
        """
        Possibly pause a producer, if there is one and the send buffer is full.
        """
        # If we are responsible for pausing our producer,
        if self.producer is not None and self.streamingProducer:
            # and our buffer is full,
            if self._isSendBufferFull():
                # pause it.
                self.producerPaused = True
                self.producer.pauseProducing()


    def write(self, data):
        """Reliably write some data.

        The data is buffered until the underlying file descriptor is ready
        for writing. If there is more than C{self.bufferSize} data in the
        buffer and this descriptor has a registered streaming producer, its
        C{pauseProducing()} method will be called.
        """
        if isinstance(data, unicode): # no, really, I mean it
            raise TypeError("Data must not be unicode")
        if not self.connected or self._writeDisconnected:
            return
        if data:
            self._tempDataBuffer.append(data)
            self._tempDataLen += len(data)
            self._maybePauseProducer()
            self.startWriting()


    def writeSequence(self, iovec):
        """
        Reliably write a sequence of data.

        Currently, this is a convenience method roughly equivalent to::

            for chunk in iovec:
                fd.write(chunk)

        It may have a more efficient implementation at a later time or in a
        different reactor.

        As with the C{write()} method, if a buffer size limit is reached and a
        streaming producer is registered, it will be paused until the buffered
        data is written to the underlying file descriptor.
        """
        for i in iovec:
            if isinstance(i, unicode): # no, really, I mean it
                raise TypeError("Data must not be unicode")
        if not self.connected or not iovec or self._writeDisconnected:
            return
        self._tempDataBuffer.extend(iovec)
        for i in iovec:
            self._tempDataLen += len(i)
        self._maybePauseProducer()
        self.startWriting()


    def loseConnection(self, _connDone=failure.Failure(main.CONNECTION_DONE)):
        """Close the connection at the next available opportunity.

        Call this to cause this FileDescriptor to lose its connection.  It will
        first write any data that it has buffered.

        If there is data buffered yet to be written, this method will cause the
        transport to lose its connection as soon as it's done flushing its
        write buffer.  If you have a producer registered, the connection won't
        be closed until the producer is finished. Therefore, make sure you
        unregister your producer when it's finished, or the connection will
        never close.
        """

        if self.connected and not self.disconnecting:
            if self._writeDisconnected:
                # doWrite won't trigger the connection close anymore
                self.stopReading()
                self.stopWriting()
                self.connectionLost(_connDone)
            else:
                self.stopReading()
                self.startWriting()
                self.disconnecting = 1

    def loseWriteConnection(self):
        self._writeDisconnecting = True
        self.startWriting()

    def stopReading(self):
        """Stop waiting for read availability.

        Call this to remove this selectable from being notified when it is
        ready for reading.
        """
        self.reactor.removeReader(self)

    def stopWriting(self):
        """Stop waiting for write availability.

        Call this to remove this selectable from being notified when it is ready
        for writing.
        """
        self.reactor.removeWriter(self)

    def startReading(self):
        """Start waiting for read availability.
        """
        self.reactor.addReader(self)

    def startWriting(self):
        """Start waiting for write availability.

        Call this to have this FileDescriptor be notified whenever it is ready for
        writing.
        """
        self.reactor.addWriter(self)

    # Producer/consumer implementation

    # first, the consumer stuff.  This requires no additional work, as
    # any object you can write to can be a consumer, really.

    producer = None
    bufferSize = 2**2**2**2

    def stopConsuming(self):
        """Stop consuming data.

        This is called when a producer has lost its connection, to tell the
        consumer to go lose its connection (and break potential circular
        references).
        """
        self.unregisterProducer()
        self.loseConnection()

    # producer interface implementation

    def resumeProducing(self):
        if self.connected and not self.disconnecting:
            self.startReading()

    def pauseProducing(self):
        self.stopReading()

    def stopProducing(self):
        self.loseConnection()


    def fileno(self):
        """File Descriptor number for select().

        This method must be overridden or assigned in subclasses to
        indicate a valid file descriptor for the operating system.
        """
        return -1


def isIPAddress(addr):
    """
    Determine whether the given string represents an IPv4 address.

    @type addr: C{str}
    @param addr: A string which may or may not be the decimal dotted
    representation of an IPv4 address.

    @rtype: C{bool}
    @return: C{True} if C{addr} represents an IPv4 address, C{False}
    otherwise.
    """
    dottedParts = addr.split('.')
    if len(dottedParts) == 4:
        for octet in dottedParts:
            try:
                value = int(octet)
            except ValueError:
                return False
            else:
                if value < 0 or value > 255:
                    return False
        return True
    return False


def isIPv6Address(addr):
    """
    Determine whether the given string represents an IPv6 address.

    @param addr: A string which may or may not be the hex
        representation of an IPv6 address.
    @type addr: C{str}

    @return: C{True} if C{addr} represents an IPv6 address, C{False}
        otherwise.
    @rtype: C{bool}
    """
    if '%' in addr:
        addr = addr.split('%', 1)[0]
    if not addr:
        return False
    try:
        # This might be a native implementation or the one from
        # twisted.python.compat.
        inet_pton(AF_INET6, addr)
    except (ValueError, error):
        return False
    return True


__all__ = ["FileDescriptor", "isIPAddress", "isIPv6Address"]
