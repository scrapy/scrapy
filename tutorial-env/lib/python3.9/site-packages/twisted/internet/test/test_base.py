# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.base}.
"""

import socket
from queue import Queue
from typing import Any, Callable
from unittest import skipIf

from zope.interface import implementer

from twisted.internet._resolver import FirstOneWins
from twisted.internet.base import DelayedCall, ReactorBase, ThreadedResolver
from twisted.internet.defer import Deferred
from twisted.internet.error import DNSLookupError
from twisted.internet.interfaces import IReactorThreads, IReactorTime, IResolverSimple
from twisted.internet.task import Clock
from twisted.python.threadpool import ThreadPool
from twisted.trial.unittest import SkipTest, TestCase

try:
    import signal as _signal
except ImportError:
    signal = None
else:
    signal = _signal


@implementer(IReactorTime, IReactorThreads)
class FakeReactor:
    """
    A fake reactor implementation which just supports enough reactor APIs for
    L{ThreadedResolver}.
    """

    def __init__(self):
        self._clock = Clock()
        self.callLater = self._clock.callLater

        self._threadpool = ThreadPool()
        self._threadpool.start()
        self.getThreadPool = lambda: self._threadpool

        self._threadCalls = Queue()

    def callFromThread(self, callable: Callable[..., Any], *args, **kwargs):
        self._threadCalls.put((callable, args, kwargs))

    def _runThreadCalls(self):
        f, args, kwargs = self._threadCalls.get()
        f(*args, **kwargs)

    def _stop(self):
        self._threadpool.stop()

    def getDelayedCalls(self):
        # IReactorTime.getDelayedCalls
        pass

    def seconds(self):
        # IReactorTime.seconds
        pass

    def callInThread(self, callable: Callable[..., Any], *args, **kwargs):
        # IReactorInThreads.callInThread
        pass

    def suggestThreadPoolSize(self, size):
        # IReactorThreads.suggestThreadPoolSize
        pass


class ThreadedResolverTests(TestCase):
    """
    Tests for L{ThreadedResolver}.
    """

    def test_success(self):
        """
        L{ThreadedResolver.getHostByName} returns a L{Deferred} which fires
        with the value returned by the call to L{socket.gethostbyname} in the
        threadpool of the reactor passed to L{ThreadedResolver.__init__}.
        """
        ip = "10.0.0.17"
        name = "foo.bar.example.com"
        timeout = 30

        reactor = FakeReactor()
        self.addCleanup(reactor._stop)

        lookedUp = []
        resolvedTo = []

        def fakeGetHostByName(name):
            lookedUp.append(name)
            return ip

        self.patch(socket, "gethostbyname", fakeGetHostByName)

        resolver = ThreadedResolver(reactor)
        d = resolver.getHostByName(name, (timeout,))
        d.addCallback(resolvedTo.append)

        reactor._runThreadCalls()

        self.assertEqual(lookedUp, [name])
        self.assertEqual(resolvedTo, [ip])

        # Make sure that any timeout-related stuff gets cleaned up.
        reactor._clock.advance(timeout + 1)
        self.assertEqual(reactor._clock.calls, [])

    def test_failure(self):
        """
        L{ThreadedResolver.getHostByName} returns a L{Deferred} which fires a
        L{Failure} if the call to L{socket.gethostbyname} raises an exception.
        """
        timeout = 30

        reactor = FakeReactor()
        self.addCleanup(reactor._stop)

        def fakeGetHostByName(name):
            raise OSError("ENOBUFS (this is a funny joke)")

        self.patch(socket, "gethostbyname", fakeGetHostByName)

        failedWith = []
        resolver = ThreadedResolver(reactor)
        d = resolver.getHostByName("some.name", (timeout,))
        self.assertFailure(d, DNSLookupError)
        d.addCallback(failedWith.append)

        reactor._runThreadCalls()

        self.assertEqual(len(failedWith), 1)

        # Make sure that any timeout-related stuff gets cleaned up.
        reactor._clock.advance(timeout + 1)
        self.assertEqual(reactor._clock.calls, [])

    def test_timeout(self):
        """
        If L{socket.gethostbyname} does not complete before the specified
        timeout elapsed, the L{Deferred} returned by
        L{ThreadedResolver.getHostByName} fails with L{DNSLookupError}.
        """
        timeout = 10

        reactor = FakeReactor()
        self.addCleanup(reactor._stop)

        result = Queue()

        def fakeGetHostByName(name):
            raise result.get()

        self.patch(socket, "gethostbyname", fakeGetHostByName)

        failedWith = []
        resolver = ThreadedResolver(reactor)
        d = resolver.getHostByName("some.name", (timeout,))
        self.assertFailure(d, DNSLookupError)
        d.addCallback(failedWith.append)

        reactor._clock.advance(timeout - 1)
        self.assertEqual(failedWith, [])
        reactor._clock.advance(1)
        self.assertEqual(len(failedWith), 1)

        # Eventually the socket.gethostbyname does finish - in this case, with
        # an exception.  Nobody cares, though.
        result.put(IOError("The I/O was errorful"))

    def test_resolverGivenStr(self):
        """
        L{ThreadedResolver.getHostByName} is passed L{str}, encoded using IDNA
        if required.
        """
        calls = []

        @implementer(IResolverSimple)
        class FakeResolver:
            def getHostByName(self, name, timeouts=()):
                calls.append(name)
                return Deferred()

        class JustEnoughReactor(ReactorBase):
            def installWaker(self):
                pass

        fake = FakeResolver()
        reactor = JustEnoughReactor()
        reactor.installResolver(fake)
        rec = FirstOneWins(Deferred())
        reactor.nameResolver.resolveHostName(rec, "example.example")
        reactor.nameResolver.resolveHostName(rec, "example.example")
        reactor.nameResolver.resolveHostName(rec, "v\xe4\xe4ntynyt.example")
        reactor.nameResolver.resolveHostName(rec, "\u0440\u0444.example")
        reactor.nameResolver.resolveHostName(rec, "xn----7sbb4ac0ad0be6cf.xn--p1ai")

        self.assertEqual(len(calls), 5)
        self.assertEqual(list(map(type, calls)), [str] * 5)
        self.assertEqual("example.example", calls[0])
        self.assertEqual("example.example", calls[1])
        self.assertEqual("xn--vntynyt-5waa.example", calls[2])
        self.assertEqual("xn--p1ai.example", calls[3])
        self.assertEqual("xn----7sbb4ac0ad0be6cf.xn--p1ai", calls[4])


def nothing():
    """
    Function used by L{DelayedCallTests.test_str}.
    """


class DelayedCallMixin:
    """
    L{DelayedCall}
    """

    def _getDelayedCallAt(self, time):
        """
        Get a L{DelayedCall} instance at a given C{time}.

        @param time: The absolute time at which the returned L{DelayedCall}
            will be scheduled.
        """

        def noop(call):
            pass

        return DelayedCall(time, lambda: None, (), {}, noop, noop, None)

    def setUp(self):
        """
        Create two L{DelayedCall} instanced scheduled to run at different
        times.
        """
        self.zero = self._getDelayedCallAt(0)
        self.one = self._getDelayedCallAt(1)

    def test_str(self):
        """
        The string representation of a L{DelayedCall} instance, as returned by
        L{str}, includes the unsigned id of the instance, as well as its state,
        the function to be called, and the function arguments.
        """
        dc = DelayedCall(12, nothing, (3,), {"A": 5}, None, None, lambda: 1.5)
        self.assertEqual(
            str(dc),
            "<DelayedCall 0x%x [10.5s] called=0 cancelled=0 nothing(3, A=5)>"
            % (id(dc),),
        )

    def test_repr(self):
        """
        The string representation of a L{DelayedCall} instance, as returned by
        {repr}, is identical to that returned by L{str}.
        """
        dc = DelayedCall(13, nothing, (6,), {"A": 9}, None, None, lambda: 1.6)
        self.assertEqual(str(dc), repr(dc))

    def test_lt(self):
        """
        For two instances of L{DelayedCall} C{a} and C{b}, C{a < b} is true
        if and only if C{a} is scheduled to run before C{b}.
        """
        zero, one = self.zero, self.one
        self.assertTrue(zero < one)
        self.assertFalse(one < zero)
        self.assertFalse(zero < zero)
        self.assertFalse(one < one)

    def test_le(self):
        """
        For two instances of L{DelayedCall} C{a} and C{b}, C{a <= b} is true
        if and only if C{a} is scheduled to run before C{b} or at the same
        time as C{b}.
        """
        zero, one = self.zero, self.one
        self.assertTrue(zero <= one)
        self.assertFalse(one <= zero)
        self.assertTrue(zero <= zero)
        self.assertTrue(one <= one)

    def test_gt(self):
        """
        For two instances of L{DelayedCall} C{a} and C{b}, C{a > b} is true
        if and only if C{a} is scheduled to run after C{b}.
        """
        zero, one = self.zero, self.one
        self.assertTrue(one > zero)
        self.assertFalse(zero > one)
        self.assertFalse(zero > zero)
        self.assertFalse(one > one)

    def test_ge(self):
        """
        For two instances of L{DelayedCall} C{a} and C{b}, C{a > b} is true
        if and only if C{a} is scheduled to run after C{b} or at the same
        time as C{b}.
        """
        zero, one = self.zero, self.one
        self.assertTrue(one >= zero)
        self.assertFalse(zero >= one)
        self.assertTrue(zero >= zero)
        self.assertTrue(one >= one)

    def test_eq(self):
        """
        A L{DelayedCall} instance is only equal to itself.
        """
        # Explicitly use == here, instead of assertEqual, to be more
        # confident __eq__ is being tested.
        self.assertFalse(self.zero == self.one)
        self.assertTrue(self.zero == self.zero)
        self.assertTrue(self.one == self.one)

    def test_ne(self):
        """
        A L{DelayedCall} instance is not equal to any other object.
        """
        # Explicitly use != here, instead of assertEqual, to be more
        # confident __ne__ is being tested.
        self.assertTrue(self.zero != self.one)
        self.assertFalse(self.zero != self.zero)
        self.assertFalse(self.one != self.one)


class DelayedCallNoDebugTests(DelayedCallMixin, TestCase):
    """
    L{DelayedCall}
    """

    def setUp(self):
        """
        Turn debug off.
        """
        self.patch(DelayedCall, "debug", False)
        DelayedCallMixin.setUp(self)

    def test_str(self):
        """
        The string representation of a L{DelayedCall} instance, as returned by
        L{str}, includes the unsigned id of the instance, as well as its state,
        the function to be called, and the function arguments.
        """
        dc = DelayedCall(12, nothing, (3,), {"A": 5}, None, None, lambda: 1.5)
        expected = (
            "<DelayedCall 0x{:x} [10.5s] called=0 cancelled=0 "
            "nothing(3, A=5)>".format(id(dc))
        )
        self.assertEqual(str(dc), expected)

    def test_switchToDebug(self):
        """
        If L{DelayedCall.debug} changes from C{0} to C{1} between
        L{DelayeCall.__init__} and L{DelayedCall.__repr__} then
        L{DelayedCall.__repr__} returns a string that does not include the
        creator stack.
        """
        dc = DelayedCall(3, lambda: None, (), {}, nothing, nothing, lambda: 2)
        dc.debug = 1
        self.assertNotIn("traceback at creation", repr(dc))


class DelayedCallDebugTests(DelayedCallMixin, TestCase):
    """
    L{DelayedCall}
    """

    def setUp(self):
        """
        Turn debug on.
        """
        self.patch(DelayedCall, "debug", True)
        DelayedCallMixin.setUp(self)

    def test_str(self):
        """
        The string representation of a L{DelayedCall} instance, as returned by
        L{str}, includes the unsigned id of the instance, as well as its state,
        the function to be called, and the function arguments.
        """
        dc = DelayedCall(12, nothing, (3,), {"A": 5}, None, None, lambda: 1.5)
        expectedRegexp = (
            "<DelayedCall 0x{:x} \\[10.5s\\] called=0 cancelled=0 "
            "nothing\\(3, A=5\\)\n\n"
            "traceback at creation:".format(id(dc))
        )
        self.assertRegex(str(dc), expectedRegexp)

    def test_switchFromDebug(self):
        """
        If L{DelayedCall.debug} changes from C{1} to C{0} between
        L{DelayeCall.__init__} and L{DelayedCall.__repr__} then
        L{DelayedCall.__repr__} returns a string that includes the creator
        stack (we captured it, we might as well display it).
        """
        dc = DelayedCall(3, lambda: None, (), {}, nothing, nothing, lambda: 2)
        dc.debug = 0
        self.assertIn("traceback at creation", repr(dc))


class TestSpySignalCapturingReactor(ReactorBase):

    """
    Subclass of ReactorBase to capture signals delivered to the
    reactor for inspection.
    """

    def installWaker(self):
        """
        Required method, unused.
        """


@skipIf(not signal, "signal module not available")
class ReactorBaseSignalTests(TestCase):

    """
    Tests to exercise ReactorBase's signal exit reporting path.
    """

    def test_exitSignalDefaultsToNone(self):
        """
        The default value of the _exitSignal attribute is None.
        """
        reactor = TestSpySignalCapturingReactor()
        self.assertIs(None, reactor._exitSignal)

    def test_captureSIGINT(self):
        """
        ReactorBase's SIGINT handler saves the value of SIGINT to the
        _exitSignal attribute.
        """
        reactor = TestSpySignalCapturingReactor()
        reactor.sigInt(signal.SIGINT, None)
        self.assertEquals(signal.SIGINT, reactor._exitSignal)

    def test_captureSIGTERM(self):
        """
        ReactorBase's SIGTERM handler saves the value of SIGTERM to the
        _exitSignal attribute.
        """
        reactor = TestSpySignalCapturingReactor()
        reactor.sigTerm(signal.SIGTERM, None)
        self.assertEquals(signal.SIGTERM, reactor._exitSignal)

    def test_captureSIGBREAK(self):
        """
        ReactorBase's SIGBREAK handler saves the value of SIGBREAK to the
        _exitSignal attribute.
        """
        if not hasattr(signal, "SIGBREAK"):
            raise SkipTest("signal module does not have SIGBREAK")

        reactor = TestSpySignalCapturingReactor()
        reactor.sigBreak(signal.SIGBREAK, None)
        self.assertEquals(signal.SIGBREAK, reactor._exitSignal)
