# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.task}.
"""

from __future__ import division, absolute_import

from twisted.trial import unittest

from twisted.internet import interfaces, task, reactor, defer, error
from twisted.internet.main import installReactor
from twisted.internet.test.modulehelpers import NoReactor

# Be compatible with any jerks who used our private stuff
Clock = task.Clock

from twisted.python import failure


class TestableLoopingCall(task.LoopingCall):
    def __init__(self, clock, *a, **kw):
        super(TestableLoopingCall, self).__init__(*a, **kw)
        self.clock = clock



class TestException(Exception):
    pass



class ClockTests(unittest.TestCase):
    """
    Test the non-wallclock based clock implementation.
    """
    def testSeconds(self):
        """
        Test that the C{seconds} method of the fake clock returns fake time.
        """
        c = task.Clock()
        self.assertEqual(c.seconds(), 0)


    def testCallLater(self):
        """
        Test that calls can be scheduled for later with the fake clock and
        hands back an L{IDelayedCall}.
        """
        c = task.Clock()
        call = c.callLater(1, lambda a, b: None, 1, b=2)
        self.assertTrue(interfaces.IDelayedCall.providedBy(call))
        self.assertEqual(call.getTime(), 1)
        self.assertTrue(call.active())


    def testCallLaterCancelled(self):
        """
        Test that calls can be cancelled.
        """
        c = task.Clock()
        call = c.callLater(1, lambda a, b: None, 1, b=2)
        call.cancel()
        self.assertFalse(call.active())


    def test_callLaterOrdering(self):
        """
        Test that the DelayedCall returned is not one previously
        created.
        """
        c = task.Clock()
        call1 = c.callLater(10, lambda a, b: None, 1, b=2)
        call2 = c.callLater(1, lambda a, b: None, 3, b=4)
        self.assertFalse(call1 is call2)


    def testAdvance(self):
        """
        Test that advancing the clock will fire some calls.
        """
        events = []
        c = task.Clock()
        call = c.callLater(2, lambda: events.append(None))
        c.advance(1)
        self.assertEqual(events, [])
        c.advance(1)
        self.assertEqual(events, [None])
        self.assertFalse(call.active())


    def testAdvanceCancel(self):
        """
        Test attempting to cancel the call in a callback.

        AlreadyCalled should be raised, not for example a ValueError from
        removing the call from Clock.calls. This requires call.called to be
        set before the callback is called.
        """
        c = task.Clock()
        def cb():
            self.assertRaises(error.AlreadyCalled, call.cancel)
        call = c.callLater(1, cb)
        c.advance(1)


    def testCallLaterDelayed(self):
        """
        Test that calls can be delayed.
        """
        events = []
        c = task.Clock()
        call = c.callLater(1, lambda a, b: events.append((a, b)), 1, b=2)
        call.delay(1)
        self.assertEqual(call.getTime(), 2)
        c.advance(1.5)
        self.assertEqual(events, [])
        c.advance(1.0)
        self.assertEqual(events, [(1, 2)])


    def testCallLaterResetLater(self):
        """
        Test that calls can have their time reset to a later time.
        """
        events = []
        c = task.Clock()
        call = c.callLater(2, lambda a, b: events.append((a, b)), 1, b=2)
        c.advance(1)
        call.reset(3)
        self.assertEqual(call.getTime(), 4)
        c.advance(2)
        self.assertEqual(events, [])
        c.advance(1)
        self.assertEqual(events, [(1, 2)])


    def testCallLaterResetSooner(self):
        """
        Test that calls can have their time reset to an earlier time.
        """
        events = []
        c = task.Clock()
        call = c.callLater(4, lambda a, b: events.append((a, b)), 1, b=2)
        call.reset(3)
        self.assertEqual(call.getTime(), 3)
        c.advance(3)
        self.assertEqual(events, [(1, 2)])


    def test_getDelayedCalls(self):
        """
        Test that we can get a list of all delayed calls
        """
        c = task.Clock()
        call = c.callLater(1, lambda x: None)
        call2 = c.callLater(2, lambda x: None)

        calls = c.getDelayedCalls()

        self.assertEqual(set([call, call2]), set(calls))


    def test_getDelayedCallsEmpty(self):
        """
        Test that we get an empty list from getDelayedCalls on a newly
        constructed Clock.
        """
        c = task.Clock()
        self.assertEqual(c.getDelayedCalls(), [])


    def test_providesIReactorTime(self):
        c = task.Clock()
        self.assertTrue(interfaces.IReactorTime.providedBy(c),
                        "Clock does not provide IReactorTime")


    def test_callLaterKeepsCallsOrdered(self):
        """
        The order of calls scheduled by L{task.Clock.callLater} is honored when
        adding a new call via calling L{task.Clock.callLater} again.

        For example, if L{task.Clock.callLater} is invoked with a callable "A"
        and a time t0, and then the L{IDelayedCall} which results from that is
        C{reset} to a later time t2 which is greater than t0, and I{then}
        L{task.Clock.callLater} is invoked again with a callable "B", and time
        t1 which is less than t2 but greater than t0, "B" will be invoked before
        "A".
        """
        result = []
        expected = [('b', 2.0), ('a', 3.0)]
        clock = task.Clock()
        logtime = lambda n: result.append((n, clock.seconds()))

        call_a = clock.callLater(1.0, logtime, "a")
        call_a.reset(3.0)
        clock.callLater(2.0, logtime, "b")

        clock.pump([1]*3)
        self.assertEqual(result, expected)


    def test_callLaterResetKeepsCallsOrdered(self):
        """
        The order of calls scheduled by L{task.Clock.callLater} is honored when
        re-scheduling an existing call via L{IDelayedCall.reset} on the result
        of a previous call to C{callLater}.

        For example, if L{task.Clock.callLater} is invoked with a callable "A"
        and a time t0, and then L{task.Clock.callLater} is invoked again with a
        callable "B", and time t1 greater than t0, and finally the
        L{IDelayedCall} for "A" is C{reset} to a later time, t2, which is
        greater than t1, "B" will be invoked before "A".
        """
        result = []
        expected = [('b', 2.0), ('a', 3.0)]
        clock = task.Clock()
        logtime = lambda n: result.append((n, clock.seconds()))

        call_a = clock.callLater(1.0, logtime, "a")
        clock.callLater(2.0, logtime, "b")
        call_a.reset(3.0)

        clock.pump([1]*3)
        self.assertEqual(result, expected)


    def test_callLaterResetInsideCallKeepsCallsOrdered(self):
        """
        The order of calls scheduled by L{task.Clock.callLater} is honored when
        re-scheduling an existing call via L{IDelayedCall.reset} on the result
        of a previous call to C{callLater}, even when that call to C{reset}
        occurs within the callable scheduled by C{callLater} itself.
        """
        result = []
        expected = [('c', 3.0), ('b', 4.0)]
        clock = task.Clock()
        logtime = lambda n: result.append((n, clock.seconds()))

        call_b = clock.callLater(2.0, logtime, "b")
        def a():
            call_b.reset(3.0)

        clock.callLater(1.0, a)
        clock.callLater(3.0, logtime, "c")

        clock.pump([0.5] * 10)
        self.assertEqual(result, expected)



class LoopTests(unittest.TestCase):
    """
    Tests for L{task.LoopingCall} based on a fake L{IReactorTime}
    implementation.
    """
    def test_defaultClock(self):
        """
        L{LoopingCall}'s default clock should be the reactor.
        """
        call = task.LoopingCall(lambda: None)
        self.assertEqual(call.clock, reactor)


    def test_callbackTimeSkips(self):
        """
        When more time than the defined interval passes during the execution
        of a callback, L{LoopingCall} should schedule the next call for the
        next interval which is still in the future.
        """
        times = []
        callDuration = None
        clock = task.Clock()
        def aCallback():
            times.append(clock.seconds())
            clock.advance(callDuration)
        call = task.LoopingCall(aCallback)
        call.clock = clock

        # Start a LoopingCall with a 0.5 second increment, and immediately call
        # the callable.
        callDuration = 2
        call.start(0.5)

        # Verify that the callable was called, and since it was immediate, with
        # no skips.
        self.assertEqual(times, [0])

        # The callback should have advanced the clock by the callDuration.
        self.assertEqual(clock.seconds(), callDuration)

        # An iteration should have occurred at 2, but since 2 is the present
        # and not the future, it is skipped.

        clock.advance(0)
        self.assertEqual(times, [0])

        # 2.5 is in the future, and is not skipped.
        callDuration = 1
        clock.advance(0.5)
        self.assertEqual(times, [0, 2.5])
        self.assertEqual(clock.seconds(), 3.5)

        # Another iteration should have occurred, but it is again the
        # present and not the future, so it is skipped as well.
        clock.advance(0)
        self.assertEqual(times, [0, 2.5])

        # 4 is in the future, and is not skipped.
        callDuration = 0
        clock.advance(0.5)
        self.assertEqual(times, [0, 2.5, 4])
        self.assertEqual(clock.seconds(), 4)


    def test_reactorTimeSkips(self):
        """
        When more time than the defined interval passes between when
        L{LoopingCall} schedules itself to run again and when it actually
        runs again, it should schedule the next call for the next interval
        which is still in the future.
        """
        times = []
        clock = task.Clock()
        def aCallback():
            times.append(clock.seconds())

        # Start a LoopingCall that tracks the time passed, with a 0.5 second
        # increment.
        call = task.LoopingCall(aCallback)
        call.clock = clock
        call.start(0.5)

        # Initially, no time should have passed!
        self.assertEqual(times, [0])

        # Advance the clock by 2 seconds (2 seconds should have passed)
        clock.advance(2)
        self.assertEqual(times, [0, 2])

        # Advance the clock by 1 second (3 total should have passed)
        clock.advance(1)
        self.assertEqual(times, [0, 2, 3])

        # Advance the clock by 0 seconds (this should have no effect!)
        clock.advance(0)
        self.assertEqual(times, [0, 2, 3])


    def test_reactorTimeCountSkips(self):
        """
        When L{LoopingCall} schedules itself to run again, if more than the
        specified interval has passed, it should schedule the next call for the
        next interval which is still in the future. If it was created
        using L{LoopingCall.withCount}, a positional argument will be
        inserted at the beginning of the argument list, indicating the number
        of calls that should have been made.
        """
        times = []
        clock = task.Clock()
        def aCallback(numCalls):
            times.append((clock.seconds(), numCalls))

        # Start a LoopingCall that tracks the time passed, and the number of
        # skips, with a 0.5 second increment.
        call = task.LoopingCall.withCount(aCallback)
        call.clock = clock
        INTERVAL = 0.5
        REALISTIC_DELAY = 0.01
        call.start(INTERVAL)

        # Initially, no seconds should have passed, and one calls should have
        # been made.
        self.assertEqual(times, [(0, 1)])

        # After the interval (plus a small delay, to account for the time that
        # the reactor takes to wake up and process the LoopingCall), we should
        # still have only made one call.
        clock.advance(INTERVAL + REALISTIC_DELAY)
        self.assertEqual(times, [(0, 1), (INTERVAL + REALISTIC_DELAY, 1)])

        # After advancing the clock by three intervals (plus a small delay to
        # account for the reactor), we should have skipped two calls; one less
        # than the number of intervals which have completely elapsed. Along
        # with the call we did actually make, the final number of calls is 3.
        clock.advance((3 * INTERVAL) + REALISTIC_DELAY)
        self.assertEqual(times,
                         [(0, 1), (INTERVAL + REALISTIC_DELAY, 1),
                          ((4 * INTERVAL) + (2 * REALISTIC_DELAY), 3)])

        # Advancing the clock by 0 seconds should not cause any changes!
        clock.advance(0)
        self.assertEqual(times,
                         [(0, 1), (INTERVAL + REALISTIC_DELAY, 1),
                          ((4 * INTERVAL) + (2 * REALISTIC_DELAY), 3)])


    def test_countLengthyIntervalCounts(self):
        """
        L{LoopingCall.withCount} counts only calls that were expected to be
        made.  So, if more than one, but less than two intervals pass between
        invocations, it won't increase the count above 1.  For example, a
        L{LoopingCall} with interval T expects to be invoked at T, 2T, 3T, etc.
        However, the reactor takes some time to get around to calling it, so in
        practice it will be called at T+something, 2T+something, 3T+something;
        and due to other things going on in the reactor, "something" is
        variable.  It won't increase the count unless "something" is greater
        than T.  So if the L{LoopingCall} is invoked at T, 2.75T, and 3T,
        the count has not increased, even though the distance between
        invocation 1 and invocation 2 is 1.75T.
        """
        times = []
        clock = task.Clock()
        def aCallback(count):
            times.append((clock.seconds(), count))

        # Start a LoopingCall that tracks the time passed, and the number of
        # calls, with a 0.5 second increment.
        call = task.LoopingCall.withCount(aCallback)
        call.clock = clock
        INTERVAL = 0.5
        REALISTIC_DELAY = 0.01
        call.start(INTERVAL)
        self.assertEqual(times.pop(), (0, 1))

        # About one interval... So far, so good
        clock.advance(INTERVAL + REALISTIC_DELAY)
        self.assertEqual(times.pop(), (INTERVAL + REALISTIC_DELAY, 1))

        # Oh no, something delayed us for a while.
        clock.advance(INTERVAL * 1.75)
        self.assertEqual(times.pop(), ((2.75 * INTERVAL) + REALISTIC_DELAY, 1))

        # Back on track!  We got invoked when we expected this time.
        clock.advance(INTERVAL * 0.25)
        self.assertEqual(times.pop(), ((3.0 * INTERVAL) + REALISTIC_DELAY, 1))


    def test_withCountFloatingPointBoundary(self):
        """
        L{task.LoopingCall.withCount} should never invoke its callable with a
        zero.  Specifically, if a L{task.LoopingCall} created with C{withCount}
        has its L{start <task.LoopingCall.start>} method invoked with a
        floating-point number which introduces decimal inaccuracy when
        multiplied or divided, such as "0.1", L{task.LoopingCall} will never
        invoke its callable with 0.  Also, the sum of all the values passed to
        its callable as the "count" will be an integer, the number of intervals
        that have elapsed.

        This is a regression test for a particularly tricky case to implement.
        """
        clock = task.Clock()
        accumulator = []
        call = task.LoopingCall.withCount(accumulator.append)
        call.clock = clock

        # 'count': the number of ticks within the time span, the number of
        # calls that should be made.  this should be a value which causes
        # floating-point inaccuracy as the denominator for the timespan.
        count = 10
        # 'timespan': the amount of virtual time that the test will take, in
        # seconds, as a floating point number
        timespan = 1.0
        # 'interval': the amount of time for one actual call.
        interval = timespan / count

        call.start(interval, now=False)
        for x in range(count):
            clock.advance(interval)

        # There is still an epsilon of inaccuracy here; 0.1 is not quite
        # exactly 1/10 in binary, so we need to push our clock over the
        # threshold.
        epsilon = timespan - sum([interval] * count)
        clock.advance(epsilon)
        secondsValue = clock.seconds()
        # The following two assertions are here to ensure that if the values of
        # count, timespan, and interval are changed, that the test remains
        # valid.  First, the "epsilon" value here measures the floating-point
        # inaccuracy in question, and so if it doesn't exist then we are not
        # triggering an interesting condition.
        self.assertTrue(abs(epsilon) > 0.0,
                        "{0} should be greater than zero"
                        .format(epsilon))
        # Secondly, task.Clock should behave in such a way that once we have
        # advanced to this point, it has reached or exceeded the timespan.
        self.assertTrue(secondsValue >= timespan,
                        "{0} should be greater than or equal to {1}"
                        .format(secondsValue, timespan))

        self.assertEqual(sum(accumulator), count)
        self.assertNotIn(0, accumulator)


    def test_withCountIntervalZero(self):
        """
        L{task.LoopingCall.withCount} with interval set to 0
        will call the countCallable 1.
        """
        clock = task.Clock()
        accumulator = []

        def foo(cnt):
            accumulator.append(cnt)
            if len(accumulator) > 4:
                loop.stop()

        loop = task.LoopingCall.withCount(foo)
        loop.clock = clock
        deferred = loop.start(0, now=False)

        clock.advance(0)
        self.successResultOf(deferred)

        self.assertEqual([1, 1, 1, 1, 1], accumulator)


    def test_withCountIntervalZeroDelay(self):
        """
        L{task.LoopingCall.withCount} with interval set to 0 and a delayed
        call during the loop run will still call the countCallable 1 as if
        no delay occurred.
        """
        clock = task.Clock()
        deferred = defer.Deferred()
        accumulator = []

        def foo(cnt):
            accumulator.append(cnt)

            if len(accumulator) == 2:
                return deferred

            if len(accumulator) > 4:
                loop.stop()

        loop = task.LoopingCall.withCount(foo)
        loop.clock = clock
        loop.start(0, now=False)

        clock.advance(0)
        # Loop will block at the third call.
        self.assertEqual([1, 1], accumulator)

        # Even if more time pass, the loops is not
        # advanced.
        clock.advance(2)
        self.assertEqual([1, 1], accumulator)

        # Once the waiting call got a result the loop continues without
        # observing any delay in countCallable.
        deferred.callback(None)
        clock.advance(0)
        self.assertEqual([1, 1, 1, 1, 1], accumulator)

    def test_withCountIntervalZeroDelayThenNonZeroInterval(self):
        """
        L{task.LoopingCall.withCount} with interval set to 0 will still keep
        the time when last called so when the interval is reset.
        """
        clock = task.Clock()
        deferred = defer.Deferred()
        accumulator = []

        def foo(cnt):
            accumulator.append(cnt)
            if len(accumulator) == 2:
                return deferred

        loop = task.LoopingCall.withCount(foo)
        loop.clock = clock
        loop.start(0, now=False)

        # Even if a lot of time pass, loop will block at the third call.
        clock.advance(10)
        self.assertEqual([1, 1], accumulator)

        # When a new interval is set, once the waiting call got a result the
        # loop continues with the new interval.
        loop.interval = 2
        deferred.callback(None)

        # It will count skipped steps since the last loop call.
        clock.advance(7)
        self.assertEqual([1, 1, 3], accumulator)

        clock.advance(2)
        self.assertEqual([1, 1, 3, 1], accumulator)

        clock.advance(4)
        self.assertEqual([1, 1, 3, 1, 2], accumulator)


    def testBasicFunction(self):
        # Arrange to have time advanced enough so that our function is
        # called a few times.
        # Only need to go to 2.5 to get 3 calls, since the first call
        # happens before any time has elapsed.
        timings = [0.05, 0.1, 0.1]

        clock = task.Clock()

        L = []
        def foo(a, b, c=None, d=None):
            L.append((a, b, c, d))

        lc = TestableLoopingCall(clock, foo, "a", "b", d="d")
        D = lc.start(0.1)

        theResult = []
        def saveResult(result):
            theResult.append(result)
        D.addCallback(saveResult)

        clock.pump(timings)

        self.assertEqual(len(L), 3,
                          "got %d iterations, not 3" % (len(L),))

        for (a, b, c, d) in L:
            self.assertEqual(a, "a")
            self.assertEqual(b, "b")
            self.assertIsNone(c)
            self.assertEqual(d, "d")

        lc.stop()
        self.assertIs(theResult[0], lc)

        # Make sure it isn't planning to do anything further.
        self.assertFalse(clock.calls)


    def testDelayedStart(self):
        timings = [0.05, 0.1, 0.1]

        clock = task.Clock()

        L = []
        lc = TestableLoopingCall(clock, L.append, None)
        d = lc.start(0.1, now=False)

        theResult = []
        def saveResult(result):
            theResult.append(result)
        d.addCallback(saveResult)

        clock.pump(timings)

        self.assertEqual(len(L), 2,
                          "got %d iterations, not 2" % (len(L),))
        lc.stop()
        self.assertIs(theResult[0], lc)

        self.assertFalse(clock.calls)


    def testBadDelay(self):
        lc = task.LoopingCall(lambda: None)
        self.assertRaises(ValueError, lc.start, -1)


    # Make sure that LoopingCall.stop() prevents any subsequent calls.
    def _stoppingTest(self, delay):
        ran = []
        def foo():
            ran.append(None)

        clock = task.Clock()
        lc = TestableLoopingCall(clock, foo)
        lc.start(delay, now=False)
        lc.stop()
        self.assertFalse(ran)
        self.assertFalse(clock.calls)


    def testStopAtOnce(self):
        return self._stoppingTest(0)


    def testStoppingBeforeDelayedStart(self):
        return self._stoppingTest(10)


    def test_reset(self):
        """
        Test that L{LoopingCall} can be reset.
        """
        ran = []
        def foo():
            ran.append(None)

        c = task.Clock()
        lc = TestableLoopingCall(c, foo)
        lc.start(2, now=False)
        c.advance(1)
        lc.reset()
        c.advance(1)
        self.assertEqual(ran, [])
        c.advance(1)
        self.assertEqual(ran, [None])


    def test_reprFunction(self):
        """
        L{LoopingCall.__repr__} includes the wrapped function's name.
        """
        self.assertEqual(repr(task.LoopingCall(installReactor, 1, key=2)),
                         "LoopingCall<None>(installReactor, *(1,), **{'key': 2})")


    def test_reprMethod(self):
        """
        L{LoopingCall.__repr__} includes the wrapped method's full name.
        """
        self.assertEqual(
            repr(task.LoopingCall(TestableLoopingCall.__init__)),
            "LoopingCall<None>(TestableLoopingCall.__init__, *(), **{})")


    def test_deferredDeprecation(self):
        """
        L{LoopingCall.deferred} is deprecated.
        """
        loop = task.LoopingCall(lambda: None)

        loop.deferred

        message = (
                'twisted.internet.task.LoopingCall.deferred was deprecated in '
                'Twisted 16.0.0; '
                'please use the deferred returned by start() instead'
                )
        warnings = self.flushWarnings([self.test_deferredDeprecation])
        self.assertEqual(1, len(warnings))
        self.assertEqual(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(message, warnings[0]['message'])



class ReactorLoopTests(unittest.TestCase):
    # Slightly inferior tests which exercise interactions with an actual
    # reactor.
    def testFailure(self):
        def foo(x):
            raise TestException(x)

        lc = task.LoopingCall(foo, "bar")
        return self.assertFailure(lc.start(0.1), TestException)


    def testFailAndStop(self):
        def foo(x):
            lc.stop()
            raise TestException(x)

        lc = task.LoopingCall(foo, "bar")
        return self.assertFailure(lc.start(0.1), TestException)


    def testEveryIteration(self):
        ran = []

        def foo():
            ran.append(None)
            if len(ran) > 5:
                lc.stop()

        lc = task.LoopingCall(foo)
        d = lc.start(0)
        def stopped(ign):
            self.assertEqual(len(ran), 6)
        return d.addCallback(stopped)


    def testStopAtOnceLater(self):
        # Ensure that even when LoopingCall.stop() is called from a
        # reactor callback, it still prevents any subsequent calls.
        d = defer.Deferred()
        def foo():
            d.errback(failure.DefaultException(
                "This task also should never get called."))
        self._lc = task.LoopingCall(foo)
        self._lc.start(1, now=False)
        reactor.callLater(0, self._callback_for_testStopAtOnceLater, d)
        return d


    def _callback_for_testStopAtOnceLater(self, d):
        self._lc.stop()
        reactor.callLater(0, d.callback, "success")

    def testWaitDeferred(self):
        # Tests if the callable isn't scheduled again before the returned
        # deferred has fired.
        timings = [0.2, 0.8]
        clock = task.Clock()

        def foo():
            d = defer.Deferred()
            d.addCallback(lambda _: lc.stop())
            clock.callLater(1, d.callback, None)
            return d

        lc = TestableLoopingCall(clock, foo)
        lc.start(0.2)
        clock.pump(timings)
        self.assertFalse(clock.calls)

    def testFailurePropagation(self):
        # Tests if the failure of the errback of the deferred returned by the
        # callable is propagated to the lc errback.
        #
        # To make sure this test does not hang trial when LoopingCall does not
        # wait for the callable's deferred, it also checks there are no
        # calls in the clock's callLater queue.
        timings = [0.3]
        clock = task.Clock()

        def foo():
            d = defer.Deferred()
            clock.callLater(0.3, d.errback, TestException())
            return d

        lc = TestableLoopingCall(clock, foo)
        d = lc.start(1)
        self.assertFailure(d, TestException)

        clock.pump(timings)
        self.assertFalse(clock.calls)
        return d


    def test_deferredWithCount(self):
        """
        In the case that the function passed to L{LoopingCall.withCount}
        returns a deferred, which does not fire before the next interval
        elapses, the function should not be run again. And if a function call
        is skipped in this fashion, the appropriate count should be
        provided.
        """
        testClock = task.Clock()
        d = defer.Deferred()
        deferredCounts = []

        def countTracker(possibleCount):
            # Keep a list of call counts
            deferredCounts.append(possibleCount)
            # Return a deferred, but only on the first request
            if len(deferredCounts) == 1:
                return d
            else:
                return None

        # Start a looping call for our countTracker function
        # Set the increment to 0.2, and do not call the function on startup.
        lc = task.LoopingCall.withCount(countTracker)
        lc.clock = testClock
        d = lc.start(0.2, now=False)

        # Confirm that nothing has happened yet.
        self.assertEqual(deferredCounts, [])

        # Advance the clock by 0.2 and then 0.4;
        testClock.pump([0.2, 0.4])
        # We should now have exactly one count (of 1 call)
        self.assertEqual(len(deferredCounts), 1)

        # Fire the deferred, and advance the clock by another 0.2
        d.callback(None)
        testClock.pump([0.2])
        # We should now have exactly 2 counts...
        self.assertEqual(len(deferredCounts), 2)
        # The first count should be 1 (one call)
        # The second count should be 3 (calls were missed at about 0.6 and 0.8)
        self.assertEqual(deferredCounts, [1, 3])



class DeferLaterTests(unittest.TestCase):
    """
    Tests for L{task.deferLater}.
    """
    def test_callback(self):
        """
        The L{Deferred} returned by L{task.deferLater} is called back after
        the specified delay with the result of the function passed in.
        """
        results = []
        flag = object()
        def callable(foo, bar):
            results.append((foo, bar))
            return flag

        clock = task.Clock()
        d = task.deferLater(clock, 3, callable, 'foo', bar='bar')
        d.addCallback(self.assertIs, flag)
        clock.advance(2)
        self.assertEqual(results, [])
        clock.advance(1)
        self.assertEqual(results, [('foo', 'bar')])
        return d


    def test_errback(self):
        """
        The L{Deferred} returned by L{task.deferLater} is errbacked if the
        supplied function raises an exception.
        """
        def callable():
            raise TestException()

        clock = task.Clock()
        d = task.deferLater(clock, 1, callable)
        clock.advance(1)
        return self.assertFailure(d, TestException)


    def test_cancel(self):
        """
        The L{Deferred} returned by L{task.deferLater} can be
        cancelled to prevent the call from actually being performed.
        """
        called = []
        clock = task.Clock()
        d = task.deferLater(clock, 1, called.append, None)
        d.cancel()
        def cbCancelled(ignored):
            # Make sure there are no calls outstanding.
            self.assertEqual([], clock.getDelayedCalls())
            # And make sure the call didn't somehow happen already.
            self.assertFalse(called)
        self.assertFailure(d, defer.CancelledError)
        d.addCallback(cbCancelled)
        return d



class _FakeReactor(object):

    def __init__(self):
        self._running = False
        self._clock = task.Clock()
        self.callLater = self._clock.callLater
        self.seconds = self._clock.seconds
        self.getDelayedCalls = self._clock.getDelayedCalls
        self._whenRunning = []
        self._shutdownTriggers = {'before': [], 'during': []}


    def callWhenRunning(self, callable, *args, **kwargs):
        if self._whenRunning is None:
            callable(*args, **kwargs)
        else:
            self._whenRunning.append((callable, args, kwargs))


    def addSystemEventTrigger(self, phase, event, callable, *args):
        assert phase in ('before', 'during')
        assert event == 'shutdown'
        self._shutdownTriggers[phase].append((callable, args))


    def run(self):
        """
        Call timed events until there are no more or the reactor is stopped.

        @raise RuntimeError: When no timed events are left and the reactor is
            still running.
        """
        self._running = True
        whenRunning = self._whenRunning
        self._whenRunning = None
        for callable, args, kwargs in whenRunning:
            callable(*args, **kwargs)
        while self._running:
            calls = self.getDelayedCalls()
            if not calls:
                raise RuntimeError("No DelayedCalls left")
            self._clock.advance(calls[0].getTime() - self.seconds())
        shutdownTriggers = self._shutdownTriggers
        self._shutdownTriggers = None
        for (trigger, args) in shutdownTriggers['before'] + shutdownTriggers['during']:
            trigger(*args)


    def stop(self):
        """
        Stop the reactor.
        """
        if not self._running:
            raise error.ReactorNotRunning()
        self._running = False



class ReactTests(unittest.SynchronousTestCase):
    """
    Tests for L{twisted.internet.task.react}.
    """

    def test_runsUntilAsyncCallback(self):
        """
        L{task.react} runs the reactor until the L{Deferred} returned by the
        function it is passed is called back, then stops it.
        """
        timePassed = []
        def main(reactor):
            finished = defer.Deferred()
            reactor.callLater(1, timePassed.append, True)
            reactor.callLater(2, finished.callback, None)
            return finished
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, _reactor=r)
        self.assertEqual(0, exitError.code)
        self.assertEqual(timePassed, [True])
        self.assertEqual(r.seconds(), 2)


    def test_runsUntilSyncCallback(self):
        """
        L{task.react} returns quickly if the L{Deferred} returned by the
        function it is passed has already been called back at the time it is
        returned.
        """
        def main(reactor):
            return defer.succeed(None)
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, _reactor=r)
        self.assertEqual(0, exitError.code)
        self.assertEqual(r.seconds(), 0)


    def test_runsUntilAsyncErrback(self):
        """
        L{task.react} runs the reactor until the L{defer.Deferred} returned by
        the function it is passed is errbacked, then it stops the reactor and
        reports the error.
        """
        class ExpectedException(Exception):
            pass

        def main(reactor):
            finished = defer.Deferred()
            reactor.callLater(1, finished.errback, ExpectedException())
            return finished
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, _reactor=r)

        self.assertEqual(1, exitError.code)

        errors = self.flushLoggedErrors(ExpectedException)
        self.assertEqual(len(errors), 1)


    def test_runsUntilSyncErrback(self):
        """
        L{task.react} returns quickly if the L{defer.Deferred} returned by the
        function it is passed has already been errbacked at the time it is
        returned.
        """
        class ExpectedException(Exception):
            pass

        def main(reactor):
            return defer.fail(ExpectedException())
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, _reactor=r)
        self.assertEqual(1, exitError.code)
        self.assertEqual(r.seconds(), 0)
        errors = self.flushLoggedErrors(ExpectedException)
        self.assertEqual(len(errors), 1)


    def test_singleStopCallback(self):
        """
        L{task.react} doesn't try to stop the reactor if the L{defer.Deferred}
        the function it is passed is called back after the reactor has already
        been stopped.
        """
        def main(reactor):
            reactor.callLater(1, reactor.stop)
            finished = defer.Deferred()
            reactor.addSystemEventTrigger(
                'during', 'shutdown', finished.callback, None)
            return finished
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, _reactor=r)
        self.assertEqual(r.seconds(), 1)

        self.assertEqual(0, exitError.code)


    def test_singleStopErrback(self):
        """
        L{task.react} doesn't try to stop the reactor if the L{defer.Deferred}
        the function it is passed is errbacked after the reactor has already
        been stopped.
        """
        class ExpectedException(Exception):
            pass

        def main(reactor):
            reactor.callLater(1, reactor.stop)
            finished = defer.Deferred()
            reactor.addSystemEventTrigger(
                'during', 'shutdown', finished.errback, ExpectedException())
            return finished
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, _reactor=r)

        self.assertEqual(1, exitError.code)

        self.assertEqual(r.seconds(), 1)
        errors = self.flushLoggedErrors(ExpectedException)
        self.assertEqual(len(errors), 1)


    def test_arguments(self):
        """
        L{task.react} passes the elements of the list it is passed as
        positional arguments to the function it is passed.
        """
        args = []
        def main(reactor, x, y, z):
            args.extend((x, y, z))
            return defer.succeed(None)
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, [1, 2, 3], _reactor=r)
        self.assertEqual(0, exitError.code)
        self.assertEqual(args, [1, 2, 3])


    def test_defaultReactor(self):
        """
        L{twisted.internet.reactor} is used if no reactor argument is passed to
        L{task.react}.
        """
        def main(reactor):
            self.passedReactor = reactor
            return defer.succeed(None)

        reactor = _FakeReactor()
        with NoReactor():
            installReactor(reactor)
            exitError = self.assertRaises(SystemExit, task.react, main, [])
            self.assertEqual(0, exitError.code)
        self.assertIs(reactor, self.passedReactor)


    def test_exitWithDefinedCode(self):
        """
        L{task.react} forwards the exit code specified by the C{SystemExit}
        error returned by the passed function, if any.
        """
        def main(reactor):
            return defer.fail(SystemExit(23))
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, [], _reactor=r)
        self.assertEqual(23, exitError.code)


    def test_synchronousStop(self):
        """
        L{task.react} handles when the reactor is stopped just before the
        returned L{Deferred} fires.
        """
        def main(reactor):
            d = defer.Deferred()
            def stop():
                reactor.stop()
                d.callback(None)
            reactor.callWhenRunning(stop)
            return d
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, [], _reactor=r)
        self.assertEqual(0, exitError.code)


    def test_asynchronousStop(self):
        """
        L{task.react} handles when the reactor is stopped and the
        returned L{Deferred} doesn't fire.
        """
        def main(reactor):
            reactor.callLater(1, reactor.stop)
            return defer.Deferred()
        r = _FakeReactor()
        exitError = self.assertRaises(
            SystemExit, task.react, main, [], _reactor=r)
        self.assertEqual(0, exitError.code)
