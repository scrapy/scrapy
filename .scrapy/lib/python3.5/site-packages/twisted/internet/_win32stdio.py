# -*- test-case-name: twisted.test.test_stdio -*-

"""
Windows-specific implementation of the L{twisted.internet.stdio} interface.
"""

import win32api
import os, msvcrt

from zope.interface import implementer

from twisted.internet.interfaces import IHalfCloseableProtocol, ITransport, IAddress
from twisted.internet.interfaces import IConsumer, IPushProducer

from twisted.internet import _pollingfile, main
from twisted.python.failure import Failure

@implementer(IAddress)
class Win32PipeAddress(object):
    pass


@implementer(ITransport, IConsumer, IPushProducer)
class StandardIO(_pollingfile._PollingTimer):

    disconnecting = False
    disconnected = False

    def __init__(self, proto, reactor=None):
        """
        Start talking to standard IO with the given protocol.

        Also, put it stdin/stdout/stderr into binary mode.
        """
        if reactor is None:
            from twisted.internet import reactor

        for stdfd in range(0, 1, 2):
            msvcrt.setmode(stdfd, os.O_BINARY)

        _pollingfile._PollingTimer.__init__(self, reactor)
        self.proto = proto

        hstdin = win32api.GetStdHandle(win32api.STD_INPUT_HANDLE)
        hstdout = win32api.GetStdHandle(win32api.STD_OUTPUT_HANDLE)

        self.stdin = _pollingfile._PollableReadPipe(
            hstdin, self.dataReceived, self.readConnectionLost)

        self.stdout = _pollingfile._PollableWritePipe(
            hstdout, self.writeConnectionLost)

        self._addPollableResource(self.stdin)
        self._addPollableResource(self.stdout)

        self.proto.makeConnection(self)

    def dataReceived(self, data):
        self.proto.dataReceived(data)

    def readConnectionLost(self):
        if IHalfCloseableProtocol.providedBy(self.proto):
            self.proto.readConnectionLost()
        self.checkConnLost()

    def writeConnectionLost(self):
        if IHalfCloseableProtocol.providedBy(self.proto):
            self.proto.writeConnectionLost()
        self.checkConnLost()

    connsLost = 0

    def checkConnLost(self):
        self.connsLost += 1
        if self.connsLost >= 2:
            self.disconnecting = True
            self.disconnected = True
            self.proto.connectionLost(Failure(main.CONNECTION_DONE))

    # ITransport

    def write(self, data):
        self.stdout.write(data)

    def writeSequence(self, seq):
        self.stdout.write(''.join(seq))

    def loseConnection(self):
        self.disconnecting = True
        self.stdin.close()
        self.stdout.close()

    def getPeer(self):
        return Win32PipeAddress()

    def getHost(self):
        return Win32PipeAddress()

    # IConsumer

    def registerProducer(self, producer, streaming):
        return self.stdout.registerProducer(producer, streaming)

    def unregisterProducer(self):
        return self.stdout.unregisterProducer()

    # def write() above

    # IProducer

    def stopProducing(self):
        self.stdin.stopProducing()

    # IPushProducer

    def pauseProducing(self):
        self.stdin.pauseProducing()

    def resumeProducing(self):
        self.stdin.resumeProducing()

