# -*- test-case-name: twisted.internet.test.test_pollingfile -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implements a simple polling interface for file descriptors that don't work with
select() - this is pretty much only useful on Windows.
"""


from zope.interface import implementer

from twisted.internet.interfaces import IConsumer, IPushProducer

MIN_TIMEOUT = 0.000000001
MAX_TIMEOUT = 0.1


class _PollableResource:
    active = True

    def activate(self):
        self.active = True

    def deactivate(self):
        self.active = False


class _PollingTimer:
    # Everything is private here because it is really an implementation detail.

    def __init__(self, reactor):
        self.reactor = reactor
        self._resources = []
        self._pollTimer = None
        self._currentTimeout = MAX_TIMEOUT
        self._paused = False

    def _addPollableResource(self, res):
        self._resources.append(res)
        self._checkPollingState()

    def _checkPollingState(self):
        for resource in self._resources:
            if resource.active:
                self._startPolling()
                break
        else:
            self._stopPolling()

    def _startPolling(self):
        if self._pollTimer is None:
            self._pollTimer = self._reschedule()

    def _stopPolling(self):
        if self._pollTimer is not None:
            self._pollTimer.cancel()
            self._pollTimer = None

    def _pause(self):
        self._paused = True

    def _unpause(self):
        self._paused = False
        self._checkPollingState()

    def _reschedule(self):
        if not self._paused:
            return self.reactor.callLater(self._currentTimeout, self._pollEvent)

    def _pollEvent(self):
        workUnits = 0.0
        anyActive = []
        for resource in self._resources:
            if resource.active:
                workUnits += resource.checkWork()
                # Check AFTER work has been done
                if resource.active:
                    anyActive.append(resource)

        newTimeout = self._currentTimeout
        if workUnits:
            newTimeout = self._currentTimeout / (workUnits + 1.0)
            if newTimeout < MIN_TIMEOUT:
                newTimeout = MIN_TIMEOUT
        else:
            newTimeout = self._currentTimeout * 2.0
            if newTimeout > MAX_TIMEOUT:
                newTimeout = MAX_TIMEOUT
        self._currentTimeout = newTimeout
        if anyActive:
            self._pollTimer = self._reschedule()


# If we ever (let's hope not) need the above functionality on UNIX, this could
# be factored into a different module.

import pywintypes  # type: ignore[import]
import win32api  # type: ignore[import]
import win32file  # type: ignore[import]
import win32pipe  # type: ignore[import]


@implementer(IPushProducer)
class _PollableReadPipe(_PollableResource):
    def __init__(self, pipe, receivedCallback, lostCallback):
        # security attributes for pipes
        self.pipe = pipe
        self.receivedCallback = receivedCallback
        self.lostCallback = lostCallback

    def checkWork(self):
        finished = 0
        fullDataRead = []

        while 1:
            try:
                buffer, bytesToRead, result = win32pipe.PeekNamedPipe(self.pipe, 1)
                # finished = (result == -1)
                if not bytesToRead:
                    break
                hr, data = win32file.ReadFile(self.pipe, bytesToRead, None)
                fullDataRead.append(data)
            except win32api.error:
                finished = 1
                break

        dataBuf = b"".join(fullDataRead)
        if dataBuf:
            self.receivedCallback(dataBuf)
        if finished:
            self.cleanup()
        return len(dataBuf)

    def cleanup(self):
        self.deactivate()
        self.lostCallback()

    def close(self):
        try:
            win32api.CloseHandle(self.pipe)
        except pywintypes.error:
            # You can't close std handles...?
            pass

    def stopProducing(self):
        self.close()

    def pauseProducing(self):
        self.deactivate()

    def resumeProducing(self):
        self.activate()


FULL_BUFFER_SIZE = 64 * 1024


@implementer(IConsumer)
class _PollableWritePipe(_PollableResource):
    def __init__(self, writePipe, lostCallback):
        self.disconnecting = False
        self.producer = None
        self.producerPaused = False
        self.streamingProducer = 0
        self.outQueue = []
        self.writePipe = writePipe
        self.lostCallback = lostCallback
        try:
            win32pipe.SetNamedPipeHandleState(
                writePipe, win32pipe.PIPE_NOWAIT, None, None
            )
        except pywintypes.error:
            # Maybe it's an invalid handle.  Who knows.
            pass

    def close(self):
        self.disconnecting = True

    def bufferFull(self):
        if self.producer is not None:
            self.producerPaused = True
            self.producer.pauseProducing()

    def bufferEmpty(self):
        if self.producer is not None and (
            (not self.streamingProducer) or self.producerPaused
        ):
            self.producer.producerPaused = False
            self.producer.resumeProducing()
            return True
        return False

    # almost-but-not-quite-exact copy-paste from abstract.FileDescriptor... ugh

    def registerProducer(self, producer, streaming):
        """Register to receive data from a producer.

        This sets this selectable to be a consumer for a producer.  When this
        selectable runs out of data on a write() call, it will ask the producer
        to resumeProducing(). A producer should implement the IProducer
        interface.

        FileDescriptor provides some infrastructure for producer methods.
        """
        if self.producer is not None:
            raise RuntimeError(
                "Cannot register producer %s, because producer %s was never "
                "unregistered." % (producer, self.producer)
            )
        if not self.active:
            producer.stopProducing()
        else:
            self.producer = producer
            self.streamingProducer = streaming
            if not streaming:
                producer.resumeProducing()

    def unregisterProducer(self):
        """Stop consuming data from a producer, without disconnecting."""
        self.producer = None

    def writeConnectionLost(self):
        self.deactivate()
        try:
            win32api.CloseHandle(self.writePipe)
        except pywintypes.error:
            # OMG what
            pass
        self.lostCallback()

    def writeSequence(self, seq):
        """
        Append a C{list} or C{tuple} of bytes to the output buffer.

        @param seq: C{list} or C{tuple} of C{str} instances to be appended to
            the output buffer.

        @raise TypeError: If C{seq} contains C{unicode}.
        """
        if str in map(type, seq):
            raise TypeError("Unicode not allowed in output buffer.")
        self.outQueue.extend(seq)

    def write(self, data):
        """
        Append some bytes to the output buffer.

        @param data: C{str} to be appended to the output buffer.
        @type data: C{str}.

        @raise TypeError: If C{data} is C{unicode} instead of C{str}.
        """
        if isinstance(data, str):
            raise TypeError("Unicode not allowed in output buffer.")
        if self.disconnecting:
            return
        self.outQueue.append(data)
        if sum(map(len, self.outQueue)) > FULL_BUFFER_SIZE:
            self.bufferFull()

    def checkWork(self):
        numBytesWritten = 0
        if not self.outQueue:
            if self.disconnecting:
                self.writeConnectionLost()
                return 0
            try:
                win32file.WriteFile(self.writePipe, b"", None)
            except pywintypes.error:
                self.writeConnectionLost()
                return numBytesWritten
        while self.outQueue:
            data = self.outQueue.pop(0)
            errCode = 0
            try:
                errCode, nBytesWritten = win32file.WriteFile(self.writePipe, data, None)
            except win32api.error:
                self.writeConnectionLost()
                break
            else:
                # assert not errCode, "wtf an error code???"
                numBytesWritten += nBytesWritten
                if len(data) > nBytesWritten:
                    self.outQueue.insert(0, data[nBytesWritten:])
                    break
        else:
            resumed = self.bufferEmpty()
            if not resumed and self.disconnecting:
                self.writeConnectionLost()
        return numBytesWritten
