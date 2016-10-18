# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.base}.
"""

import socket
try:
    from Queue import Queue
except ImportError:
    from queue import Queue

from zope.interface import implementer

from twisted.python.threadpool import ThreadPool
from twisted.internet.interfaces import IReactorTime, IReactorThreads
from twisted.internet.error import DNSLookupError
from twisted.internet.base import ThreadedResolver, DelayedCall
from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase


@implementer(IReactorTime, IReactorThreads)
class FakeReactor(object):
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


    def callFromThread(self, f, *args, **kwargs):
        self._threadCalls.put((f, args, kwargs))


    def _runThreadCalls(self):
        f, args, kwargs = self._threadCalls.get()
        f(*args, **kwargs)


    def _stop(self):
        self._threadpool.stop()



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

        self.patch(socket, 'gethostbyname', fakeGetHostByName)

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
            raise IOError("ENOBUFS (this is a funny joke)")

        self.patch(socket, 'gethostbyname', fakeGetHostByName)

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
        L{ThreadedResolver.getHostByBame} fails with L{DNSLookupError}.
        """
        timeout = 10

        reactor = FakeReactor()
        self.addCleanup(reactor._stop)

        result = Queue()
        def fakeGetHostByName(name):
            raise result.get()

        self.patch(socket, 'gethostbyname', fakeGetHostByName)

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



def nothing():
    """
    Function used by L{DelayedCallTests.test_str}.
    """


class DelayedCallTests(TestCase):
    """
    Tests for L{DelayedCall}.
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
        C{str}, includes the unsigned id of the instance, as well as its state,
        the function to be called, and the function arguments.
        """
        dc = DelayedCall(12, nothing, (3, ), {"A": 5}, None, None, lambda: 1.5)
        self.assertEqual(
            str(dc),
            "<DelayedCall 0x%x [10.5s] called=0 cancelled=0 nothing(3, A=5)>"
                % (id(dc),))


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
