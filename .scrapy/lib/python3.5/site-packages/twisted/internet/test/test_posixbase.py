# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.posixbase} and supporting code.
"""

from __future__ import division, absolute_import

from twisted.trial.unittest import TestCase
from twisted.internet.defer import Deferred
from twisted.internet.posixbase import PosixReactorBase, _Waker
from twisted.internet.protocol import ServerFactory

skipSockets = None
try:
    from twisted.internet import unix
    from twisted.test.test_unix import ClientProto
except ImportError:
    skipSockets = "Platform does not support AF_UNIX sockets"

from twisted.internet.tcp import Port
from twisted.internet import reactor




class TrivialReactor(PosixReactorBase):
    def __init__(self):
        self._readers = {}
        self._writers = {}
        PosixReactorBase.__init__(self)


    def addReader(self, reader):
        self._readers[reader] = True


    def removeReader(self, reader):
        del self._readers[reader]


    def addWriter(self, writer):
        self._writers[writer] = True


    def removeWriter(self, writer):
        del self._writers[writer]



class PosixReactorBaseTests(TestCase):
    """
    Tests for L{PosixReactorBase}.
    """

    def _checkWaker(self, reactor):
        self.assertIsInstance(reactor.waker, _Waker)
        self.assertIn(reactor.waker, reactor._internalReaders)
        self.assertIn(reactor.waker, reactor._readers)


    def test_wakerIsInternalReader(self):
        """
        When L{PosixReactorBase} is instantiated, it creates a waker and adds
        it to its internal readers set.
        """
        reactor = TrivialReactor()
        self._checkWaker(reactor)


    def test_removeAllSkipsInternalReaders(self):
        """
        Any L{IReadDescriptors} in L{PosixReactorBase._internalReaders} are
        left alone by L{PosixReactorBase._removeAll}.
        """
        reactor = TrivialReactor()
        extra = object()
        reactor._internalReaders.add(extra)
        reactor.addReader(extra)
        reactor._removeAll(reactor._readers, reactor._writers)
        self._checkWaker(reactor)
        self.assertIn(extra, reactor._internalReaders)
        self.assertIn(extra, reactor._readers)


    def test_removeAllReturnsRemovedDescriptors(self):
        """
        L{PosixReactorBase._removeAll} returns a list of removed
        L{IReadDescriptor} and L{IWriteDescriptor} objects.
        """
        reactor = TrivialReactor()
        reader = object()
        writer = object()
        reactor.addReader(reader)
        reactor.addWriter(writer)
        removed = reactor._removeAll(
            reactor._readers, reactor._writers)
        self.assertEqual(set(removed), set([reader, writer]))
        self.assertNotIn(reader, reactor._readers)
        self.assertNotIn(writer, reactor._writers)



class TCPPortTests(TestCase):
    """
    Tests for L{twisted.internet.tcp.Port}.
    """

    if not isinstance(reactor, PosixReactorBase):
        skip = "Non-posixbase reactor"

    def test_connectionLostFailed(self):
        """
        L{Port.stopListening} returns a L{Deferred} which errbacks if
        L{Port.connectionLost} raises an exception.
        """
        port = Port(12345, ServerFactory())
        port.connected = True
        port.connectionLost = lambda reason: 1 // 0
        return self.assertFailure(port.stopListening(), ZeroDivisionError)



class TimeoutReportReactor(PosixReactorBase):
    """
    A reactor which is just barely runnable and which cannot monitor any
    readers or writers, and which fires a L{Deferred} with the timeout
    passed to its C{doIteration} method as soon as that method is invoked.
    """
    def __init__(self):
        PosixReactorBase.__init__(self)
        self.iterationTimeout = Deferred()
        self.now = 100


    def addReader(self, reader):
        """
        Ignore the reader.  This is necessary because the waker will be
        added.  However, we won't actually monitor it for any events.
        """


    def removeAll(self):
        """
        There are no readers or writers, so there is nothing to remove.
        This will be called when the reactor stops, though, so it must be
        implemented.
        """
        return []


    def seconds(self):
        """
        Override the real clock with a deterministic one that can be easily
        controlled in a unit test.
        """
        return self.now


    def doIteration(self, timeout):
        d = self.iterationTimeout
        if d is not None:
            self.iterationTimeout = None
            d.callback(timeout)



class IterationTimeoutTests(TestCase):
    """
    Tests for the timeout argument L{PosixReactorBase.run} calls
    L{PosixReactorBase.doIteration} with in the presence of various delayed
    calls.
    """
    def _checkIterationTimeout(self, reactor):
        timeout = []
        reactor.iterationTimeout.addCallback(timeout.append)
        reactor.iterationTimeout.addCallback(lambda ignored: reactor.stop())
        reactor.run()
        return timeout[0]


    def test_noCalls(self):
        """
        If there are no delayed calls, C{doIteration} is called with a
        timeout of L{None}.
        """
        reactor = TimeoutReportReactor()
        timeout = self._checkIterationTimeout(reactor)
        self.assertIsNone(timeout)


    def test_delayedCall(self):
        """
        If there is a delayed call, C{doIteration} is called with a timeout
        which is the difference between the current time and the time at
        which that call is to run.
        """
        reactor = TimeoutReportReactor()
        reactor.callLater(100, lambda: None)
        timeout = self._checkIterationTimeout(reactor)
        self.assertEqual(timeout, 100)


    def test_timePasses(self):
        """
        If a delayed call is scheduled and then some time passes, the
        timeout passed to C{doIteration} is reduced by the amount of time
        which passed.
        """
        reactor = TimeoutReportReactor()
        reactor.callLater(100, lambda: None)
        reactor.now += 25
        timeout = self._checkIterationTimeout(reactor)
        self.assertEqual(timeout, 75)


    def test_multipleDelayedCalls(self):
        """
        If there are several delayed calls, C{doIteration} is called with a
        timeout which is the difference between the current time and the
        time at which the earlier of the two calls is to run.
        """
        reactor = TimeoutReportReactor()
        reactor.callLater(50, lambda: None)
        reactor.callLater(10, lambda: None)
        reactor.callLater(100, lambda: None)
        timeout = self._checkIterationTimeout(reactor)
        self.assertEqual(timeout, 10)


    def test_resetDelayedCall(self):
        """
        If a delayed call is reset, the timeout passed to C{doIteration} is
        based on the interval between the time when reset is called and the
        new delay of the call.
        """
        reactor = TimeoutReportReactor()
        call = reactor.callLater(50, lambda: None)
        reactor.now += 25
        call.reset(15)
        timeout = self._checkIterationTimeout(reactor)
        self.assertEqual(timeout, 15)


    def test_delayDelayedCall(self):
        """
        If a delayed call is re-delayed, the timeout passed to
        C{doIteration} is based on the remaining time before the call would
        have been made and the additional amount of time passed to the delay
        method.
        """
        reactor = TimeoutReportReactor()
        call = reactor.callLater(50, lambda: None)
        reactor.now += 10
        call.delay(20)
        timeout = self._checkIterationTimeout(reactor)
        self.assertEqual(timeout, 60)


    def test_cancelDelayedCall(self):
        """
        If the only delayed call is canceled, L{None} is the timeout passed
        to C{doIteration}.
        """
        reactor = TimeoutReportReactor()
        call = reactor.callLater(50, lambda: None)
        call.cancel()
        timeout = self._checkIterationTimeout(reactor)
        self.assertIsNone(timeout)



class ConnectedDatagramPortTests(TestCase):
    """
    Test connected datagram UNIX sockets.
    """
    if skipSockets is not None:
        skip = skipSockets


    def test_connectionFailedDoesntCallLoseConnection(self):
        """
        L{ConnectedDatagramPort} does not call the deprecated C{loseConnection}
        in L{ConnectedDatagramPort.connectionFailed}.
        """
        def loseConnection():
            """
            Dummy C{loseConnection} method. C{loseConnection} is deprecated and
            should not get called.
            """
            self.fail("loseConnection is deprecated and should not get called.")

        port = unix.ConnectedDatagramPort(None, ClientProto())
        port.loseConnection = loseConnection
        port.connectionFailed("goodbye")


    def test_connectionFailedCallsStopListening(self):
        """
        L{ConnectedDatagramPort} calls L{ConnectedDatagramPort.stopListening}
        instead of the deprecated C{loseConnection} in
        L{ConnectedDatagramPort.connectionFailed}.
        """
        self.called = False

        def stopListening():
            """
            Dummy C{stopListening} method.
            """
            self.called = True

        port = unix.ConnectedDatagramPort(None, ClientProto())
        port.stopListening = stopListening
        port.connectionFailed("goodbye")
        self.assertTrue(self.called)
