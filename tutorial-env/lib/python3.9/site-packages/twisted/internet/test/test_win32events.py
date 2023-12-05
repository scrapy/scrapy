# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorWin32Events}.
"""

try:
    import win32event  # type: ignore[import]
except ImportError:
    win32event = None

from zope.interface.verify import verifyObject

from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IReactorWin32Events
from twisted.internet.test.reactormixins import ReactorBuilder
from twisted.python.failure import Failure
from twisted.python.threadable import getThreadID, isInIOThread


class Listener:
    """
    L{Listener} is an object that can be added to a L{IReactorWin32Events}
    reactor to receive callback notification when a Windows event is set.  It
    records what thread its callback is invoked in and fires a Deferred.

    @ivar success: A flag which is set to C{True} when the event callback is
        called.

    @ivar logThreadID: The id of the thread in which the C{logPrefix} method is
        called.

    @ivar eventThreadID: The id of the thread in which the event callback is
        called.

    @ivar connLostThreadID: The id of the thread in which the C{connectionLost}
        method is called.

    @ivar _finished: The L{Deferred} which will be fired when the event callback
        is called.
    """

    success = False
    logThreadID = eventThreadID = connLostThreadID = None

    def __init__(self, finished):
        self._finished = finished

    def logPrefix(self):
        self.logThreadID = getThreadID()
        return "Listener"

    def occurred(self):
        self.success = True
        self.eventThreadID = getThreadID()
        self._finished.callback(None)

    def brokenOccurred(self):
        raise RuntimeError("Some problem")

    def returnValueOccurred(self):
        return EnvironmentError("Entirely different problem")

    def connectionLost(self, reason):
        self.connLostThreadID = getThreadID()
        self._finished.errback(reason)


class Win32EventsTestsBuilder(ReactorBuilder):
    """
    Builder defining tests relating to L{IReactorWin32Events}.
    """

    requiredInterfaces = [IReactorWin32Events]

    def test_interface(self):
        """
        An instance of the reactor has all of the methods defined on
        L{IReactorWin32Events}.
        """
        reactor = self.buildReactor()
        verifyObject(IReactorWin32Events, reactor)

    def test_addEvent(self):
        """
        When an event which has been added to the reactor is set, the action
        associated with the event is invoked in the reactor thread.
        """
        reactorThreadID = getThreadID()
        reactor = self.buildReactor()
        event = win32event.CreateEvent(None, False, False, None)
        finished = Deferred()
        finished.addCallback(lambda ignored: reactor.stop())
        listener = Listener(finished)
        reactor.addEvent(event, listener, "occurred")
        reactor.callWhenRunning(win32event.SetEvent, event)
        self.runReactor(reactor)
        self.assertTrue(listener.success)
        self.assertEqual(reactorThreadID, listener.logThreadID)
        self.assertEqual(reactorThreadID, listener.eventThreadID)

    def test_ioThreadDoesNotChange(self):
        """
        Using L{IReactorWin32Events.addEvent} does not change which thread is
        reported as the I/O thread.
        """
        results = []

        def check(ignored):
            results.append(isInIOThread())
            reactor.stop()

        reactor = self.buildReactor()
        event = win32event.CreateEvent(None, False, False, None)
        finished = Deferred()
        listener = Listener(finished)
        finished.addCallback(check)
        reactor.addEvent(event, listener, "occurred")
        reactor.callWhenRunning(win32event.SetEvent, event)
        self.runReactor(reactor)
        self.assertTrue(listener.success)
        self.assertEqual([True], results)

    def test_disconnectedOnError(self):
        """
        If the event handler raises an exception, the event is removed from the
        reactor and the handler's C{connectionLost} method is called in the I/O
        thread and the exception is logged.
        """
        reactorThreadID = getThreadID()
        reactor = self.buildReactor()
        event = win32event.CreateEvent(None, False, False, None)

        result = []
        finished = Deferred()
        finished.addBoth(result.append)
        finished.addBoth(lambda ignored: reactor.stop())

        listener = Listener(finished)
        reactor.addEvent(event, listener, "brokenOccurred")
        reactor.callWhenRunning(win32event.SetEvent, event)
        self.runReactor(reactor)

        self.assertIsInstance(result[0], Failure)
        result[0].trap(RuntimeError)

        self.assertEqual(reactorThreadID, listener.connLostThreadID)
        self.assertEqual(1, len(self.flushLoggedErrors(RuntimeError)))

    def test_disconnectOnReturnValue(self):
        """
        If the event handler returns a value, the event is removed from the
        reactor and the handler's C{connectionLost} method is called in the I/O
        thread.
        """
        reactorThreadID = getThreadID()
        reactor = self.buildReactor()
        event = win32event.CreateEvent(None, False, False, None)

        result = []
        finished = Deferred()
        finished.addBoth(result.append)
        finished.addBoth(lambda ignored: reactor.stop())

        listener = Listener(finished)
        reactor.addEvent(event, listener, "returnValueOccurred")
        reactor.callWhenRunning(win32event.SetEvent, event)
        self.runReactor(reactor)

        self.assertIsInstance(result[0], Failure)
        result[0].trap(EnvironmentError)

        self.assertEqual(reactorThreadID, listener.connLostThreadID)

    def test_notDisconnectedOnShutdown(self):
        """
        Event handlers added with L{IReactorWin32Events.addEvent} do not have
        C{connectionLost} called on them if they are still active when the
        reactor shuts down.
        """
        reactor = self.buildReactor()
        event = win32event.CreateEvent(None, False, False, None)
        finished = Deferred()
        listener = Listener(finished)
        reactor.addEvent(event, listener, "occurred")
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        self.assertIsNone(listener.connLostThreadID)


globals().update(Win32EventsTestsBuilder.makeTestCaseClasses())
