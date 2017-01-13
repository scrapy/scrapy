# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Abstract file handle class
"""

from twisted.internet import main, error, interfaces
from twisted.internet.abstract import _ConsumerMixin, _LogOwner
from twisted.python import failure

from zope.interface import implementer
import errno

from twisted.internet.iocpreactor.const import ERROR_HANDLE_EOF
from twisted.internet.iocpreactor.const import ERROR_IO_PENDING
from twisted.internet.iocpreactor import iocpsupport as _iocp


@implementer(interfaces.IPushProducer, interfaces.IConsumer,
             interfaces.ITransport, interfaces.IHalfCloseableDescriptor)
class FileHandle(_ConsumerMixin, _LogOwner):
    """
    File handle that can read and write asynchronously
    """
    # read stuff
    maxReadBuffers = 16
    readBufferSize = 4096
    reading = False
    dynamicReadBuffers = True # set this to false if subclass doesn't do iovecs
    _readNextBuffer = 0
    _readSize = 0 # how much data we have in the read buffer
    _readScheduled = None
    _readScheduledInOS = False


    def startReading(self):
        self.reactor.addActiveHandle(self)
        if not self._readScheduled and not self.reading:
            self.reading = True
            self._readScheduled = self.reactor.callLater(0,
                                                         self._resumeReading)


    def stopReading(self):
        if self._readScheduled:
            self._readScheduled.cancel()
            self._readScheduled = None
        self.reading = False


    def _resumeReading(self):
        self._readScheduled = None
        if self._dispatchData() and not self._readScheduledInOS:
            self.doRead()


    def _dispatchData(self):
        """
        Dispatch previously read data. Return True if self.reading and we don't
        have any more data
        """
        if not self._readSize:
            return self.reading
        size = self._readSize
        full_buffers = size // self.readBufferSize
        while self._readNextBuffer < full_buffers:
            self.dataReceived(self._readBuffers[self._readNextBuffer])
            self._readNextBuffer += 1
            if not self.reading:
                return False
        remainder = size % self.readBufferSize
        if remainder:
            self.dataReceived(buffer(self._readBuffers[full_buffers],
                                     0, remainder))
        if self.dynamicReadBuffers:
            total_buffer_size = self.readBufferSize * len(self._readBuffers)
            # we have one buffer too many
            if size < total_buffer_size - self.readBufferSize:
                del self._readBuffers[-1]
            # we filled all buffers, so allocate one more
            elif (size == total_buffer_size and
                  len(self._readBuffers) < self.maxReadBuffers):
                self._readBuffers.append(bytearray(self.readBufferSize))
        self._readNextBuffer = 0
        self._readSize = 0
        return self.reading


    def _cbRead(self, rc, bytes, evt):
        self._readScheduledInOS = False
        if self._handleRead(rc, bytes, evt):
            self.doRead()


    def _handleRead(self, rc, bytes, evt):
        """
        Returns False if we should stop reading for now
        """
        if self.disconnected:
            return False
        # graceful disconnection
        if (not (rc or bytes)) or rc in (errno.WSAEDISCON, ERROR_HANDLE_EOF):
            self.reactor.removeActiveHandle(self)
            self.readConnectionLost(failure.Failure(main.CONNECTION_DONE))
            return False
        # XXX: not handling WSAEWOULDBLOCK
        # ("too many outstanding overlapped I/O requests")
        elif rc:
            self.connectionLost(failure.Failure(
                                error.ConnectionLost("read error -- %s (%s)" %
                                    (errno.errorcode.get(rc, 'unknown'), rc))))
            return False
        else:
            assert self._readSize == 0
            assert self._readNextBuffer == 0
            self._readSize = bytes
            return self._dispatchData()


    def doRead(self):
        evt = _iocp.Event(self._cbRead, self)

        evt.buff = buff = self._readBuffers
        rc, bytes = self.readFromHandle(buff, evt)

        if not rc or rc == ERROR_IO_PENDING:
            self._readScheduledInOS = True
        else:
            self._handleRead(rc, bytes, evt)


    def readFromHandle(self, bufflist, evt):
        raise NotImplementedError() # TODO: this should default to ReadFile


    def dataReceived(self, data):
        raise NotImplementedError


    def readConnectionLost(self, reason):
        self.connectionLost(reason)


    # write stuff
    dataBuffer = ''
    offset = 0
    writing = False
    _writeScheduled = None
    _writeDisconnecting = False
    _writeDisconnected = False
    writeBufferSize = 2**2**2**2


    def loseWriteConnection(self):
        self._writeDisconnecting = True
        self.startWriting()


    def _closeWriteConnection(self):
        # override in subclasses
        pass


    def writeConnectionLost(self, reason):
        # in current code should never be called
        self.connectionLost(reason)


    def startWriting(self):
        self.reactor.addActiveHandle(self)
        self.writing = True
        if not self._writeScheduled:
            self._writeScheduled = self.reactor.callLater(0,
                                                          self._resumeWriting)


    def stopWriting(self):
        if self._writeScheduled:
            self._writeScheduled.cancel()
            self._writeScheduled = None
        self.writing = False


    def _resumeWriting(self):
        self._writeScheduled = None
        self.doWrite()


    def _cbWrite(self, rc, bytes, evt):
        if self._handleWrite(rc, bytes, evt):
            self.doWrite()


    def _handleWrite(self, rc, bytes, evt):
        """
        Returns false if we should stop writing for now
        """
        if self.disconnected or self._writeDisconnected:
            return False
        # XXX: not handling WSAEWOULDBLOCK
        # ("too many outstanding overlapped I/O requests")
        if rc:
            self.connectionLost(failure.Failure(
                                error.ConnectionLost("write error -- %s (%s)" %
                                    (errno.errorcode.get(rc, 'unknown'), rc))))
            return False
        else:
            self.offset += bytes
            # If there is nothing left to send,
            if self.offset == len(self.dataBuffer) and not self._tempDataLen:
                self.dataBuffer = ""
                self.offset = 0
                # stop writing
                self.stopWriting()
                # If I've got a producer who is supposed to supply me with data
                if self.producer is not None and ((not self.streamingProducer)
                                                  or self.producerPaused):
                    # tell them to supply some more.
                    self.producerPaused = True
                    self.producer.resumeProducing()
                elif self.disconnecting:
                    # But if I was previously asked to let the connection die,
                    # do so.
                    self.connectionLost(failure.Failure(main.CONNECTION_DONE))
                elif self._writeDisconnecting:
                    # I was previously asked to half-close the connection.
                    self._writeDisconnected = True
                    self._closeWriteConnection()
                return False
            else:
                return True


    def doWrite(self):
        if len(self.dataBuffer) - self.offset < self.SEND_LIMIT:
            # If there is currently less than SEND_LIMIT bytes left to send
            # in the string, extend it with the array data.
            self.dataBuffer = (buffer(self.dataBuffer, self.offset) +
                               "".join(self._tempDataBuffer))
            self.offset = 0
            self._tempDataBuffer = []
            self._tempDataLen = 0

        evt = _iocp.Event(self._cbWrite, self)

        # Send as much data as you can.
        if self.offset:
            evt.buff = buff = buffer(self.dataBuffer, self.offset)
        else:
            evt.buff = buff = self.dataBuffer
        rc, bytes = self.writeToHandle(buff, evt)
        if rc and rc != ERROR_IO_PENDING:
            self._handleWrite(rc, bytes, evt)


    def writeToHandle(self, buff, evt):
        raise NotImplementedError() # TODO: this should default to WriteFile


    def write(self, data):
        """Reliably write some data.

        The data is buffered until his file descriptor is ready for writing.
        """
        if isinstance(data, unicode): # no, really, I mean it
            raise TypeError("Data must not be unicode")
        if not self.connected or self._writeDisconnected:
            return
        if data:
            self._tempDataBuffer.append(data)
            self._tempDataLen += len(data)
            if self.producer is not None and self.streamingProducer:
                if (len(self.dataBuffer) + self._tempDataLen
                    > self.writeBufferSize):
                    self.producerPaused = True
                    self.producer.pauseProducing()
            self.startWriting()


    def writeSequence(self, iovec):
        for i in iovec:
            if isinstance(i, unicode): # no, really, I mean it
                raise TypeError("Data must not be unicode")
        if not self.connected or not iovec or self._writeDisconnected:
            return
        self._tempDataBuffer.extend(iovec)
        for i in iovec:
            self._tempDataLen += len(i)
        if self.producer is not None and self.streamingProducer:
            if len(self.dataBuffer) + self._tempDataLen > self.writeBufferSize:
                self.producerPaused = True
                self.producer.pauseProducing()
        self.startWriting()


    # general stuff
    connected = False
    disconnected = False
    disconnecting = False
    logstr = "Uninitialized"

    SEND_LIMIT = 128*1024


    def __init__(self, reactor = None):
        if not reactor:
            from twisted.internet import reactor
        self.reactor = reactor
        self._tempDataBuffer = [] # will be added to dataBuffer in doWrite
        self._tempDataLen = 0
        self._readBuffers = [bytearray(self.readBufferSize)]


    def connectionLost(self, reason):
        """
        The connection was lost.

        This is called when the connection on a selectable object has been
        lost.  It will be called whether the connection was closed explicitly,
        an exception occurred in an event handler, or the other end of the
        connection closed it first.

        Clean up state here, but make sure to call back up to FileDescriptor.
        """

        self.disconnected = True
        self.connected = False
        if self.producer is not None:
            self.producer.stopProducing()
            self.producer = None
        self.stopReading()
        self.stopWriting()
        self.reactor.removeActiveHandle(self)


    def getFileHandle(self):
        return -1


    def loseConnection(self, _connDone=failure.Failure(main.CONNECTION_DONE)):
        """
        Close the connection at the next available opportunity.

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
                self.stopWriting
                self.connectionLost(_connDone)
            else:
                self.stopReading()
                self.startWriting()
                self.disconnecting = 1


    # Producer/consumer implementation

    def stopConsuming(self):
        """
        Stop consuming data.

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


__all__ = ['FileHandle']
