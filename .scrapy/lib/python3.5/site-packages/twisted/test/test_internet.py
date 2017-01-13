# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for lots of functionality provided by L{twisted.internet}.
"""

from __future__ import division, absolute_import

import os
import sys
import time

from twisted.python.compat import _PY3
from twisted.trial import unittest
from twisted.internet import reactor, protocol, error, abstract, defer
from twisted.internet import interfaces, base

try:
    from twisted.internet import ssl
except ImportError:
    ssl = None
if ssl and not ssl.supported:
    ssl = None

from twisted.internet.defer import Deferred
if not _PY3:
    from twisted.python import util


class ThreePhaseEventTests(unittest.TestCase):
    """
    Tests for the private implementation helpers for system event triggers.
    """
    def setUp(self):
        """
        Create a trigger, an argument, and an event to be used by tests.
        """
        self.trigger = lambda x: None
        self.arg = object()
        self.event = base._ThreePhaseEvent()


    def test_addInvalidPhase(self):
        """
        L{_ThreePhaseEvent.addTrigger} should raise L{KeyError} when called
        with an invalid phase.
        """
        self.assertRaises(
            KeyError,
            self.event.addTrigger, 'xxx', self.trigger, self.arg)


    def test_addBeforeTrigger(self):
        """
        L{_ThreePhaseEvent.addTrigger} should accept C{'before'} as a phase, a
        callable, and some arguments and add the callable with the arguments to
        the before list.
        """
        self.event.addTrigger('before', self.trigger, self.arg)
        self.assertEqual(
            self.event.before,
            [(self.trigger, (self.arg,), {})])


    def test_addDuringTrigger(self):
        """
        L{_ThreePhaseEvent.addTrigger} should accept C{'during'} as a phase, a
        callable, and some arguments and add the callable with the arguments to
        the during list.
        """
        self.event.addTrigger('during', self.trigger, self.arg)
        self.assertEqual(
            self.event.during,
            [(self.trigger, (self.arg,), {})])


    def test_addAfterTrigger(self):
        """
        L{_ThreePhaseEvent.addTrigger} should accept C{'after'} as a phase, a
        callable, and some arguments and add the callable with the arguments to
        the after list.
        """
        self.event.addTrigger('after', self.trigger, self.arg)
        self.assertEqual(
            self.event.after,
            [(self.trigger, (self.arg,), {})])


    def test_removeTrigger(self):
        """
        L{_ThreePhaseEvent.removeTrigger} should accept an opaque object
        previously returned by L{_ThreePhaseEvent.addTrigger} and remove the
        associated trigger.
        """
        handle = self.event.addTrigger('before', self.trigger, self.arg)
        self.event.removeTrigger(handle)
        self.assertEqual(self.event.before, [])


    def test_removeNonexistentTrigger(self):
        """
        L{_ThreePhaseEvent.removeTrigger} should raise L{ValueError} when given
        an object not previously returned by L{_ThreePhaseEvent.addTrigger}.
        """
        self.assertRaises(ValueError, self.event.removeTrigger, object())


    def test_removeRemovedTrigger(self):
        """
        L{_ThreePhaseEvent.removeTrigger} should raise L{ValueError} the second
        time it is called with an object returned by
        L{_ThreePhaseEvent.addTrigger}.
        """
        handle = self.event.addTrigger('before', self.trigger, self.arg)
        self.event.removeTrigger(handle)
        self.assertRaises(ValueError, self.event.removeTrigger, handle)


    def test_removeAlmostValidTrigger(self):
        """
        L{_ThreePhaseEvent.removeTrigger} should raise L{ValueError} if it is
        given a trigger handle which resembles a valid trigger handle aside
        from its phase being incorrect.
        """
        self.assertRaises(
            KeyError,
            self.event.removeTrigger, ('xxx', self.trigger, (self.arg,), {}))


    def test_fireEvent(self):
        """
        L{_ThreePhaseEvent.fireEvent} should call I{before}, I{during}, and
        I{after} phase triggers in that order.
        """
        events = []
        self.event.addTrigger('after', events.append, ('first', 'after'))
        self.event.addTrigger('during', events.append, ('first', 'during'))
        self.event.addTrigger('before', events.append, ('first', 'before'))
        self.event.addTrigger('before', events.append, ('second', 'before'))
        self.event.addTrigger('during', events.append, ('second', 'during'))
        self.event.addTrigger('after', events.append, ('second', 'after'))

        self.assertEqual(events, [])
        self.event.fireEvent()
        self.assertEqual(events,
                         [('first', 'before'), ('second', 'before'),
                          ('first', 'during'), ('second', 'during'),
                          ('first', 'after'), ('second', 'after')])


    def test_asynchronousBefore(self):
        """
        L{_ThreePhaseEvent.fireEvent} should wait for any L{Deferred} returned
        by a I{before} phase trigger before proceeding to I{during} events.
        """
        events = []
        beforeResult = Deferred()
        self.event.addTrigger('before', lambda: beforeResult)
        self.event.addTrigger('during', events.append, 'during')
        self.event.addTrigger('after', events.append, 'after')

        self.assertEqual(events, [])
        self.event.fireEvent()
        self.assertEqual(events, [])
        beforeResult.callback(None)
        self.assertEqual(events, ['during', 'after'])


    def test_beforeTriggerException(self):
        """
        If a before-phase trigger raises a synchronous exception, it should be
        logged and the remaining triggers should be run.
        """
        events = []

        class DummyException(Exception):
            pass

        def raisingTrigger():
            raise DummyException()

        self.event.addTrigger('before', raisingTrigger)
        self.event.addTrigger('before', events.append, 'before')
        self.event.addTrigger('during', events.append, 'during')
        self.event.fireEvent()
        self.assertEqual(events, ['before', 'during'])
        errors = self.flushLoggedErrors(DummyException)
        self.assertEqual(len(errors), 1)


    def test_duringTriggerException(self):
        """
        If a during-phase trigger raises a synchronous exception, it should be
        logged and the remaining triggers should be run.
        """
        events = []

        class DummyException(Exception):
            pass

        def raisingTrigger():
            raise DummyException()

        self.event.addTrigger('during', raisingTrigger)
        self.event.addTrigger('during', events.append, 'during')
        self.event.addTrigger('after', events.append, 'after')
        self.event.fireEvent()
        self.assertEqual(events, ['during', 'after'])
        errors = self.flushLoggedErrors(DummyException)
        self.assertEqual(len(errors), 1)


    def test_synchronousRemoveAlreadyExecutedBefore(self):
        """
        If a before-phase trigger tries to remove another before-phase trigger
        which has already run, a warning should be emitted.
        """
        events = []

        def removeTrigger():
            self.event.removeTrigger(beforeHandle)

        beforeHandle = self.event.addTrigger('before', events.append, ('first', 'before'))
        self.event.addTrigger('before', removeTrigger)
        self.event.addTrigger('before', events.append, ('second', 'before'))
        self.assertWarns(
            DeprecationWarning,
            "Removing already-fired system event triggers will raise an "
            "exception in a future version of Twisted.",
            __file__,
            self.event.fireEvent)
        self.assertEqual(events, [('first', 'before'), ('second', 'before')])


    def test_synchronousRemovePendingBefore(self):
        """
        If a before-phase trigger removes another before-phase trigger which
        has not yet run, the removed trigger should not be run.
        """
        events = []
        self.event.addTrigger(
            'before', lambda: self.event.removeTrigger(beforeHandle))
        beforeHandle = self.event.addTrigger(
            'before', events.append, ('first', 'before'))
        self.event.addTrigger('before', events.append, ('second', 'before'))
        self.event.fireEvent()
        self.assertEqual(events, [('second', 'before')])


    def test_synchronousBeforeRemovesDuring(self):
        """
        If a before-phase trigger removes a during-phase trigger, the
        during-phase trigger should not be run.
        """
        events = []
        self.event.addTrigger(
            'before', lambda: self.event.removeTrigger(duringHandle))
        duringHandle = self.event.addTrigger('during', events.append, 'during')
        self.event.addTrigger('after', events.append, 'after')
        self.event.fireEvent()
        self.assertEqual(events, ['after'])


    def test_asynchronousBeforeRemovesDuring(self):
        """
        If a before-phase trigger returns a L{Deferred} and later removes a
        during-phase trigger before the L{Deferred} fires, the during-phase
        trigger should not be run.
        """
        events = []
        beforeResult = Deferred()
        self.event.addTrigger('before', lambda: beforeResult)
        duringHandle = self.event.addTrigger('during', events.append, 'during')
        self.event.addTrigger('after', events.append, 'after')
        self.event.fireEvent()
        self.event.removeTrigger(duringHandle)
        beforeResult.callback(None)
        self.assertEqual(events, ['after'])


    def test_synchronousBeforeRemovesConspicuouslySimilarDuring(self):
        """
        If a before-phase trigger removes a during-phase trigger which is
        identical to an already-executed before-phase trigger aside from their
        phases, no warning should be emitted and the during-phase trigger
        should not be run.
        """
        events = []
        def trigger():
            events.append('trigger')
        self.event.addTrigger('before', trigger)
        self.event.addTrigger(
            'before', lambda: self.event.removeTrigger(duringTrigger))
        duringTrigger = self.event.addTrigger('during', trigger)
        self.event.fireEvent()
        self.assertEqual(events, ['trigger'])


    def test_synchronousRemovePendingDuring(self):
        """
        If a during-phase trigger removes another during-phase trigger which
        has not yet run, the removed trigger should not be run.
        """
        events = []
        self.event.addTrigger(
            'during', lambda: self.event.removeTrigger(duringHandle))
        duringHandle = self.event.addTrigger(
            'during', events.append, ('first', 'during'))
        self.event.addTrigger(
            'during', events.append, ('second', 'during'))
        self.event.fireEvent()
        self.assertEqual(events, [('second', 'during')])


    def test_triggersRunOnce(self):
        """
        A trigger should only be called on the first call to
        L{_ThreePhaseEvent.fireEvent}.
        """
        events = []
        self.event.addTrigger('before', events.append, 'before')
        self.event.addTrigger('during', events.append, 'during')
        self.event.addTrigger('after', events.append, 'after')
        self.event.fireEvent()
        self.event.fireEvent()
        self.assertEqual(events, ['before', 'during', 'after'])


    def test_finishedBeforeTriggersCleared(self):
        """
        The temporary list L{_ThreePhaseEvent.finishedBefore} should be emptied
        and the state reset to C{'BASE'} before the first during-phase trigger
        executes.
        """
        events = []
        def duringTrigger():
            events.append('during')
            self.assertEqual(self.event.finishedBefore, [])
            self.assertEqual(self.event.state, 'BASE')
        self.event.addTrigger('before', events.append, 'before')
        self.event.addTrigger('during', duringTrigger)
        self.event.fireEvent()
        self.assertEqual(events, ['before', 'during'])



class SystemEventTests(unittest.TestCase):
    """
    Tests for the reactor's implementation of the C{fireSystemEvent},
    C{addSystemEventTrigger}, and C{removeSystemEventTrigger} methods of the
    L{IReactorCore} interface.

    @ivar triggers: A list of the handles to triggers which have been added to
        the reactor.
    """
    def setUp(self):
        """
        Create an empty list in which to store trigger handles.
        """
        self.triggers = []


    def tearDown(self):
        """
        Remove all remaining triggers from the reactor.
        """
        while self.triggers:
            trigger = self.triggers.pop()
            try:
                reactor.removeSystemEventTrigger(trigger)
            except (ValueError, KeyError):
                pass


    def addTrigger(self, event, phase, func):
        """
        Add a trigger to the reactor and remember it in C{self.triggers}.
        """
        t = reactor.addSystemEventTrigger(event, phase, func)
        self.triggers.append(t)
        return t


    def removeTrigger(self, trigger):
        """
        Remove a trigger by its handle from the reactor and from
        C{self.triggers}.
        """
        reactor.removeSystemEventTrigger(trigger)
        self.triggers.remove(trigger)


    def _addSystemEventTriggerTest(self, phase):
        eventType = 'test'
        events = []
        def trigger():
            events.append(None)
        self.addTrigger(phase, eventType, trigger)
        self.assertEqual(events, [])
        reactor.fireSystemEvent(eventType)
        self.assertEqual(events, [None])


    def test_beforePhase(self):
        """
        L{IReactorCore.addSystemEventTrigger} should accept the C{'before'}
        phase and not call the given object until the right event is fired.
        """
        self._addSystemEventTriggerTest('before')


    def test_duringPhase(self):
        """
        L{IReactorCore.addSystemEventTrigger} should accept the C{'during'}
        phase and not call the given object until the right event is fired.
        """
        self._addSystemEventTriggerTest('during')


    def test_afterPhase(self):
        """
        L{IReactorCore.addSystemEventTrigger} should accept the C{'after'}
        phase and not call the given object until the right event is fired.
        """
        self._addSystemEventTriggerTest('after')


    def test_unknownPhase(self):
        """
        L{IReactorCore.addSystemEventTrigger} should reject phases other than
        C{'before'}, C{'during'}, or C{'after'}.
        """
        eventType = 'test'
        self.assertRaises(
            KeyError, self.addTrigger, 'xxx', eventType, lambda: None)


    def test_beforePreceedsDuring(self):
        """
        L{IReactorCore.addSystemEventTrigger} should call triggers added to the
        C{'before'} phase before it calls triggers added to the C{'during'}
        phase.
        """
        eventType = 'test'
        events = []
        def beforeTrigger():
            events.append('before')
        def duringTrigger():
            events.append('during')
        self.addTrigger('before', eventType, beforeTrigger)
        self.addTrigger('during', eventType, duringTrigger)
        self.assertEqual(events, [])
        reactor.fireSystemEvent(eventType)
        self.assertEqual(events, ['before', 'during'])


    def test_duringPreceedsAfter(self):
        """
        L{IReactorCore.addSystemEventTrigger} should call triggers added to the
        C{'during'} phase before it calls triggers added to the C{'after'}
        phase.
        """
        eventType = 'test'
        events = []
        def duringTrigger():
            events.append('during')
        def afterTrigger():
            events.append('after')
        self.addTrigger('during', eventType, duringTrigger)
        self.addTrigger('after', eventType, afterTrigger)
        self.assertEqual(events, [])
        reactor.fireSystemEvent(eventType)
        self.assertEqual(events, ['during', 'after'])


    def test_beforeReturnsDeferred(self):
        """
        If a trigger added to the C{'before'} phase of an event returns a
        L{Deferred}, the C{'during'} phase should be delayed until it is called
        back.
        """
        triggerDeferred = Deferred()
        eventType = 'test'
        events = []
        def beforeTrigger():
            return triggerDeferred
        def duringTrigger():
            events.append('during')
        self.addTrigger('before', eventType, beforeTrigger)
        self.addTrigger('during', eventType, duringTrigger)
        self.assertEqual(events, [])
        reactor.fireSystemEvent(eventType)
        self.assertEqual(events, [])
        triggerDeferred.callback(None)
        self.assertEqual(events, ['during'])


    def test_multipleBeforeReturnDeferred(self):
        """
        If more than one trigger added to the C{'before'} phase of an event
        return L{Deferred}s, the C{'during'} phase should be delayed until they
        are all called back.
        """
        firstDeferred = Deferred()
        secondDeferred = Deferred()
        eventType = 'test'
        events = []
        def firstBeforeTrigger():
            return firstDeferred
        def secondBeforeTrigger():
            return secondDeferred
        def duringTrigger():
            events.append('during')
        self.addTrigger('before', eventType, firstBeforeTrigger)
        self.addTrigger('before', eventType, secondBeforeTrigger)
        self.addTrigger('during', eventType, duringTrigger)
        self.assertEqual(events, [])
        reactor.fireSystemEvent(eventType)
        self.assertEqual(events, [])
        firstDeferred.callback(None)
        self.assertEqual(events, [])
        secondDeferred.callback(None)
        self.assertEqual(events, ['during'])


    def test_subsequentBeforeTriggerFiresPriorBeforeDeferred(self):
        """
        If a trigger added to the C{'before'} phase of an event calls back a
        L{Deferred} returned by an earlier trigger in the C{'before'} phase of
        the same event, the remaining C{'before'} triggers for that event
        should be run and any further L{Deferred}s waited on before proceeding
        to the C{'during'} events.
        """
        eventType = 'test'
        events = []
        firstDeferred = Deferred()
        secondDeferred = Deferred()
        def firstBeforeTrigger():
            return firstDeferred
        def secondBeforeTrigger():
            firstDeferred.callback(None)
        def thirdBeforeTrigger():
            events.append('before')
            return secondDeferred
        def duringTrigger():
            events.append('during')
        self.addTrigger('before', eventType, firstBeforeTrigger)
        self.addTrigger('before', eventType, secondBeforeTrigger)
        self.addTrigger('before', eventType, thirdBeforeTrigger)
        self.addTrigger('during', eventType, duringTrigger)
        self.assertEqual(events, [])
        reactor.fireSystemEvent(eventType)
        self.assertEqual(events, ['before'])
        secondDeferred.callback(None)
        self.assertEqual(events, ['before', 'during'])


    def test_removeSystemEventTrigger(self):
        """
        A trigger removed with L{IReactorCore.removeSystemEventTrigger} should
        not be called when the event fires.
        """
        eventType = 'test'
        events = []
        def firstBeforeTrigger():
            events.append('first')
        def secondBeforeTrigger():
            events.append('second')
        self.addTrigger('before', eventType, firstBeforeTrigger)
        self.removeTrigger(
            self.addTrigger('before', eventType, secondBeforeTrigger))
        self.assertEqual(events, [])
        reactor.fireSystemEvent(eventType)
        self.assertEqual(events, ['first'])


    def test_removeNonExistentSystemEventTrigger(self):
        """
        Passing an object to L{IReactorCore.removeSystemEventTrigger} which was
        not returned by a previous call to
        L{IReactorCore.addSystemEventTrigger} or which has already been passed
        to C{removeSystemEventTrigger} should result in L{TypeError},
        L{KeyError}, or L{ValueError} being raised.
        """
        b = self.addTrigger('during', 'test', lambda: None)
        self.removeTrigger(b)
        self.assertRaises(
            TypeError, reactor.removeSystemEventTrigger, None)
        self.assertRaises(
            ValueError, reactor.removeSystemEventTrigger, b)
        self.assertRaises(
            KeyError,
            reactor.removeSystemEventTrigger,
            (b[0], ('xxx',) + b[1][1:]))


    def test_interactionBetweenDifferentEvents(self):
        """
        L{IReactorCore.fireSystemEvent} should behave the same way for a
        particular system event regardless of whether Deferreds are being
        waited on for a different system event.
        """
        events = []

        firstEvent = 'first-event'
        firstDeferred = Deferred()
        def beforeFirstEvent():
            events.append(('before', 'first'))
            return firstDeferred
        def afterFirstEvent():
            events.append(('after', 'first'))

        secondEvent = 'second-event'
        secondDeferred = Deferred()
        def beforeSecondEvent():
            events.append(('before', 'second'))
            return secondDeferred
        def afterSecondEvent():
            events.append(('after', 'second'))

        self.addTrigger('before', firstEvent, beforeFirstEvent)
        self.addTrigger('after', firstEvent, afterFirstEvent)
        self.addTrigger('before', secondEvent, beforeSecondEvent)
        self.addTrigger('after', secondEvent, afterSecondEvent)

        self.assertEqual(events, [])

        # After this, firstEvent should be stuck before 'during' waiting for
        # firstDeferred.
        reactor.fireSystemEvent(firstEvent)
        self.assertEqual(events, [('before', 'first')])

        # After this, secondEvent should be stuck before 'during' waiting for
        # secondDeferred.
        reactor.fireSystemEvent(secondEvent)
        self.assertEqual(events, [('before', 'first'), ('before', 'second')])

        # After this, firstEvent should have finished completely, but
        # secondEvent should be at the same place.
        firstDeferred.callback(None)
        self.assertEqual(events, [('before', 'first'), ('before', 'second'),
                                  ('after', 'first')])

        # After this, secondEvent should have finished completely.
        secondDeferred.callback(None)
        self.assertEqual(events, [('before', 'first'), ('before', 'second'),
                                  ('after', 'first'), ('after', 'second')])



class TimeTests(unittest.TestCase):
    """
    Tests for the IReactorTime part of the reactor.
    """


    def test_seconds(self):
        """
        L{twisted.internet.reactor.seconds} should return something
        like a number.

        1. This test specifically does not assert any relation to the
           "system time" as returned by L{time.time} or
           L{twisted.python.runtime.seconds}, because at some point we
           may find a better option for scheduling calls than
           wallclock-time.
        2. This test *also* does not assert anything about the type of
           the result, because operations may not return ints or
           floats: For example, datetime-datetime == timedelta(0).
        """
        now = reactor.seconds()
        self.assertEqual(now-now+now, now)


    def test_callLaterUsesReactorSecondsInDelayedCall(self):
        """
        L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}
        should use the reactor's seconds factory
        to produce the time at which the DelayedCall will be called.
        """
        oseconds = reactor.seconds
        reactor.seconds = lambda: 100
        try:
            call = reactor.callLater(5, lambda: None)
            self.assertEqual(call.getTime(), 105)
        finally:
            reactor.seconds = oseconds


    def test_callLaterUsesReactorSecondsAsDelayedCallSecondsFactory(self):
        """
        L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}
        should propagate its own seconds factory
        to the DelayedCall to use as its own seconds factory.
        """
        oseconds = reactor.seconds
        reactor.seconds = lambda: 100
        try:
            call = reactor.callLater(5, lambda: None)
            self.assertEqual(call.seconds(), 100)
        finally:
            reactor.seconds = oseconds


    def test_callLater(self):
        """
        Test that a DelayedCall really calls the function it is
        supposed to call.
        """
        d = Deferred()
        reactor.callLater(0, d.callback, None)
        d.addCallback(self.assertEqual, None)
        return d


    def test_cancelDelayedCall(self):
        """
        Test that when a DelayedCall is cancelled it does not run.
        """
        called = []
        def function():
            called.append(None)
        call = reactor.callLater(0, function)
        call.cancel()

        # Schedule a call in two "iterations" to check to make sure that the
        # above call never ran.
        d = Deferred()
        def check():
            try:
                self.assertEqual(called, [])
            except:
                d.errback()
            else:
                d.callback(None)
        reactor.callLater(0, reactor.callLater, 0, check)
        return d


    def test_cancelCancelledDelayedCall(self):
        """
        Test that cancelling a DelayedCall which has already been cancelled
        raises the appropriate exception.
        """
        call = reactor.callLater(0, lambda: None)
        call.cancel()
        self.assertRaises(error.AlreadyCancelled, call.cancel)


    def test_cancelCalledDelayedCallSynchronous(self):
        """
        Test that cancelling a DelayedCall in the DelayedCall's function as
        that function is being invoked by the DelayedCall raises the
        appropriate exception.
        """
        d = Deferred()
        def later():
            try:
                self.assertRaises(error.AlreadyCalled, call.cancel)
            except:
                d.errback()
            else:
                d.callback(None)
        call = reactor.callLater(0, later)
        return d


    def test_cancelCalledDelayedCallAsynchronous(self):
        """
        Test that cancelling a DelayedCall after it has run its function
        raises the appropriate exception.
        """
        d = Deferred()
        def check():
            try:
                self.assertRaises(error.AlreadyCalled, call.cancel)
            except:
                d.errback()
            else:
                d.callback(None)
        def later():
            reactor.callLater(0, check)
        call = reactor.callLater(0, later)
        return d


    def testCallLaterTime(self):
        d = reactor.callLater(10, lambda: None)
        try:
            self.assertTrue(d.getTime() - (time.time() + 10) < 1)
        finally:
            d.cancel()


    def testDelayedCallStringification(self):
        # Mostly just make sure str() isn't going to raise anything for
        # DelayedCalls within reason.
        dc = reactor.callLater(0, lambda x, y: None, 'x', y=10)
        str(dc)
        dc.reset(5)
        str(dc)
        dc.cancel()
        str(dc)

        dc = reactor.callLater(0, lambda: None, x=[({'hello': u'world'}, 10j), reactor], *range(10))
        str(dc)
        dc.cancel()
        str(dc)

        def calledBack(ignored):
            str(dc)
        d = Deferred().addCallback(calledBack)
        dc = reactor.callLater(0, d.callback, None)
        str(dc)
        return d


    def testDelayedCallSecondsOverride(self):
        """
        Test that the C{seconds} argument to DelayedCall gets used instead of
        the default timing function, if it is not None.
        """
        def seconds():
            return 10
        dc = base.DelayedCall(5, lambda: None, (), {}, lambda dc: None,
                              lambda dc: None, seconds)
        self.assertEqual(dc.getTime(), 5)
        dc.reset(3)
        self.assertEqual(dc.getTime(), 13)


class CallFromThreadStopsAndWakeUpTests(unittest.TestCase):
    def testWakeUp(self):
        # Make sure other threads can wake up the reactor
        d = Deferred()
        def wake():
            time.sleep(0.1)
            # callFromThread will call wakeUp for us
            reactor.callFromThread(d.callback, None)
        reactor.callInThread(wake)
        return d

    if interfaces.IReactorThreads(reactor, None) is None:
        testWakeUp.skip = "Nothing to wake up for without thread support"

    def _stopCallFromThreadCallback(self):
        self.stopped = True

    def _callFromThreadCallback(self, d):
        reactor.callFromThread(self._callFromThreadCallback2, d)
        reactor.callLater(0, self._stopCallFromThreadCallback)

    def _callFromThreadCallback2(self, d):
        try:
            self.assertTrue(self.stopped)
        except:
            # Send the error to the deferred
            d.errback()
        else:
            d.callback(None)

    def testCallFromThreadStops(self):
        """
        Ensure that callFromThread from inside a callFromThread
        callback doesn't sit in an infinite loop and lets other
        things happen too.
        """
        self.stopped = False
        d = defer.Deferred()
        reactor.callFromThread(self._callFromThreadCallback, d)
        return d


class DelayedTests(unittest.TestCase):
    def setUp(self):
        self.finished = 0
        self.counter = 0
        self.timers = {}
        self.deferred = defer.Deferred()

    def tearDown(self):
        for t in self.timers.values():
            t.cancel()

    def checkTimers(self):
        l1 = self.timers.values()
        l2 = list(reactor.getDelayedCalls())

        # There should be at least the calls we put in.  There may be other
        # calls that are none of our business and that we should ignore,
        # though.

        missing = []
        for dc in l1:
            if dc not in l2:
                missing.append(dc)
        if missing:
            self.finished = 1
        self.assertFalse(missing, "Should have been missing no calls, instead "
                         + "was missing " + repr(missing))

    def callback(self, tag):
        del self.timers[tag]
        self.checkTimers()

    def addCallback(self, tag):
        self.callback(tag)
        self.addTimer(15, self.callback)

    def done(self, tag):
        self.finished = 1
        self.callback(tag)
        self.deferred.callback(None)

    def addTimer(self, when, callback):
        self.timers[self.counter] = reactor.callLater(when * 0.01, callback,
                                                      self.counter)
        self.counter += 1
        self.checkTimers()

    def testGetDelayedCalls(self):
        if not hasattr(reactor, "getDelayedCalls"):
            return
        # This is not a race because we don't do anything which might call
        # the reactor until we have all the timers set up. If we did, this
        # test might fail on slow systems.
        self.checkTimers()
        self.addTimer(35, self.done)
        self.addTimer(20, self.callback)
        self.addTimer(30, self.callback)
        which = self.counter
        self.addTimer(29, self.callback)
        self.addTimer(25, self.addCallback)
        self.addTimer(26, self.callback)

        self.timers[which].cancel()
        del self.timers[which]
        self.checkTimers()

        self.deferred.addCallback(lambda x : self.checkTimers())
        return self.deferred


    def test_active(self):
        """
        L{IDelayedCall.active} returns False once the call has run.
        """
        dcall = reactor.callLater(0.01, self.deferred.callback, True)
        self.assertTrue(dcall.active())

        def checkDeferredCall(success):
            self.assertFalse(dcall.active())
            return success

        self.deferred.addCallback(checkDeferredCall)

        return self.deferred



resolve_helper = """
from __future__ import print_function
import %(reactor)s
%(reactor)s.install()
from twisted.internet import reactor

class Foo:
    def __init__(self):
        reactor.callWhenRunning(self.start)
        self.timer = reactor.callLater(3, self.failed)
    def start(self):
        reactor.resolve('localhost').addBoth(self.done)
    def done(self, res):
        print('done', res)
        reactor.stop()
    def failed(self):
        print('failed')
        self.timer = None
        reactor.stop()
f = Foo()
reactor.run()
"""

class ChildResolveProtocol(protocol.ProcessProtocol):
    def __init__(self, onCompletion):
        self.onCompletion = onCompletion

    def connectionMade(self):
        self.output = []
        self.error = []

    def outReceived(self, out):
        self.output.append(out)

    def errReceived(self, err):
        self.error.append(err)

    def processEnded(self, reason):
        self.onCompletion.callback((reason, self.output, self.error))
        self.onCompletion = None


class ResolveTests(unittest.TestCase):
    def testChildResolve(self):
        # I've seen problems with reactor.run under gtk2reactor. Spawn a
        # child which just does reactor.resolve after the reactor has
        # started, fail if it does not complete in a timely fashion.
        helperPath = os.path.abspath(self.mktemp())
        with open(helperPath, 'w') as helperFile:

            # Eeueuuggg
            reactorName = reactor.__module__

            helperFile.write(resolve_helper % {'reactor': reactorName})

        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join(sys.path)

        helperDeferred = Deferred()
        helperProto = ChildResolveProtocol(helperDeferred)

        reactor.spawnProcess(helperProto, sys.executable, ("python", "-u", helperPath), env)

        def cbFinished(result):
            (reason, output, error) = result
            # If the output is "done 127.0.0.1\n" we don't really care what
            # else happened.
            output = b''.join(output)
            if output != b'done 127.0.0.1\n':
                self.fail((
                    "The child process failed to produce the desired results:\n"
                    "   Reason for termination was: %r\n"
                    "   Output stream was: %r\n"
                    "   Error stream was: %r\n") % (reason.getErrorMessage(), output, b''.join(error)))

        helperDeferred.addCallback(cbFinished)
        return helperDeferred

if not interfaces.IReactorProcess(reactor, None):
    ResolveTests.skip = (
        "cannot run test: reactor doesn't support IReactorProcess")



class CallFromThreadTests(unittest.TestCase):
    """
    Task scheduling from threads tests.
    """
    if interfaces.IReactorThreads(reactor, None) is None:
        skip = "Nothing to test without thread support"

    def setUp(self):
        self.counter = 0
        self.deferred = Deferred()


    def schedule(self, *args, **kwargs):
        """
        Override in subclasses.
        """
        reactor.callFromThread(*args, **kwargs)


    def test_lotsOfThreadsAreScheduledCorrectly(self):
        """
        L{IReactorThreads.callFromThread} can be used to schedule a large
        number of calls in the reactor thread.
        """
        def addAndMaybeFinish():
            self.counter += 1
            if self.counter == 100:
                self.deferred.callback(True)

        for i in range(100):
            self.schedule(addAndMaybeFinish)

        return self.deferred


    def test_threadsAreRunInScheduledOrder(self):
        """
        Callbacks should be invoked in the order they were scheduled.
        """
        order = []

        def check(_):
            self.assertEqual(order, [1, 2, 3])

        self.deferred.addCallback(check)
        self.schedule(order.append, 1)
        self.schedule(order.append, 2)
        self.schedule(order.append, 3)
        self.schedule(reactor.callFromThread, self.deferred.callback, None)

        return self.deferred


    def test_scheduledThreadsNotRunUntilReactorRuns(self):
        """
        Scheduled tasks should not be run until the reactor starts running.
        """
        def incAndFinish():
            self.counter = 1
            self.deferred.callback(True)
        self.schedule(incAndFinish)

        # Callback shouldn't have fired yet.
        self.assertEqual(self.counter, 0)

        return self.deferred



class MyProtocol(protocol.Protocol):
    """
    Sample protocol.
    """

class MyFactory(protocol.Factory):
    """
    Sample factory.
    """

    protocol = MyProtocol


class ProtocolTests(unittest.TestCase):

    def testFactory(self):
        factory = MyFactory()
        protocol = factory.buildProtocol(None)
        self.assertEqual(protocol.factory, factory)
        self.assertIsInstance(protocol, factory.protocol)


class DummyProducer(object):
    """
    Very uninteresting producer implementation used by tests to ensure the
    right methods are called by the consumer with which it is registered.

    @type events: C{list} of C{str}
    @ivar events: The producer/consumer related events which have happened to
    this producer.  Strings in this list may be C{'resume'}, C{'stop'}, or
    C{'pause'}.  Elements are added as they occur.
    """

    def __init__(self):
        self.events = []


    def resumeProducing(self):
        self.events.append('resume')


    def stopProducing(self):
        self.events.append('stop')


    def pauseProducing(self):
        self.events.append('pause')



class SillyDescriptor(abstract.FileDescriptor):
    """
    A descriptor whose data buffer gets filled very fast.

    Useful for testing FileDescriptor's IConsumer interface, since
    the data buffer fills as soon as at least four characters are
    written to it, and gets emptied in a single doWrite() cycle.
    """
    bufferSize = 3
    connected = True

    def writeSomeData(self, data):
        """
        Always write all data.
        """
        return len(data)


    def startWriting(self):
        """
        Do nothing: bypass the reactor.
        """
    stopWriting = startWriting



class ReentrantProducer(DummyProducer):
    """
    Similar to L{DummyProducer}, but with a resumeProducing method which calls
    back into an L{IConsumer} method of the consumer against which it is
    registered.

    @ivar consumer: The consumer with which this producer has been or will
    be registered.

    @ivar methodName: The name of the method to call on the consumer inside
    C{resumeProducing}.

    @ivar methodArgs: The arguments to pass to the consumer method invoked in
    C{resumeProducing}.
    """
    def __init__(self, consumer, methodName, *methodArgs):
        super(ReentrantProducer, self).__init__()
        self.consumer = consumer
        self.methodName = methodName
        self.methodArgs = methodArgs


    def resumeProducing(self):
        super(ReentrantProducer, self).resumeProducing()
        getattr(self.consumer, self.methodName)(*self.methodArgs)



class ProducerTests(unittest.TestCase):
    """
    Test abstract.FileDescriptor's consumer interface.
    """
    def test_doubleProducer(self):
        """
        Verify that registering a non-streaming producer invokes its
        resumeProducing() method and that you can only register one producer
        at a time.
        """
        fd = abstract.FileDescriptor()
        fd.connected = 1
        dp = DummyProducer()
        fd.registerProducer(dp, 0)
        self.assertEqual(dp.events, ['resume'])
        self.assertRaises(RuntimeError, fd.registerProducer, DummyProducer(), 0)


    def test_unconnectedFileDescriptor(self):
        """
        Verify that registering a producer when the connection has already
        been closed invokes its stopProducing() method.
        """
        fd = abstract.FileDescriptor()
        fd.disconnected = 1
        dp = DummyProducer()
        fd.registerProducer(dp, 0)
        self.assertEqual(dp.events, ['stop'])


    def _dontPausePullConsumerTest(self, methodName):
        """
        Pull consumers don't get their C{pauseProducing} method called if the
        descriptor buffer fills up.

        @param _methodName: Either 'write', or 'writeSequence', indicating
            which transport method to write data to.
        """
        descriptor = SillyDescriptor()
        producer = DummyProducer()
        descriptor.registerProducer(producer, streaming=False)
        self.assertEqual(producer.events, ['resume'])
        del producer.events[:]

        # Fill up the descriptor's write buffer so we can observe whether or
        # not it pauses its producer in that case.
        if methodName == "writeSequence":
            descriptor.writeSequence([b'1', b'2', b'3', b'4'])
        else:
            descriptor.write(b'1234')

        self.assertEqual(producer.events, [])


    def test_dontPausePullConsumerOnWrite(self):
        """
        Verify that FileDescriptor does not call producer.pauseProducing() on a
        non-streaming pull producer in response to a L{IConsumer.write} call
        which results in a full write buffer. Issue #2286.
        """
        return self._dontPausePullConsumerTest('write')


    def test_dontPausePullConsumerOnWriteSequence(self):
        """
        Like L{test_dontPausePullConsumerOnWrite}, but for a call to
        C{writeSequence} rather than L{IConsumer.write}.

        C{writeSequence} is not part of L{IConsumer}, but
        L{abstract.FileDescriptor} has supported consumery behavior in response
        to calls to L{writeSequence} forever.
        """
        return self._dontPausePullConsumerTest('writeSequence')


    def _reentrantStreamingProducerTest(self, methodName):
        descriptor = SillyDescriptor()
        if methodName == "writeSequence":
            data = [b's', b'p', b'am']
        else:
            data = b"spam"
        producer = ReentrantProducer(descriptor, methodName, data)
        descriptor.registerProducer(producer, streaming=True)

        # Start things off by filling up the descriptor's buffer so it will
        # pause its producer.
        getattr(descriptor, methodName)(data)

        # Sanity check - make sure that worked.
        self.assertEqual(producer.events, ['pause'])
        del producer.events[:]

        # After one call to doWrite, the buffer has been emptied so the
        # FileDescriptor should resume its producer.  That will result in an
        # immediate call to FileDescriptor.write which will again fill the
        # buffer and result in the producer being paused.
        descriptor.doWrite()
        self.assertEqual(producer.events, ['resume', 'pause'])
        del producer.events[:]

        # After a second call to doWrite, the exact same thing should have
        # happened.  Prior to the bugfix for which this test was written,
        # FileDescriptor would have incorrectly believed its producer was
        # already resumed (it was paused) and so not resume it again.
        descriptor.doWrite()
        self.assertEqual(producer.events, ['resume', 'pause'])


    def test_reentrantStreamingProducerUsingWrite(self):
        """
        Verify that FileDescriptor tracks producer's paused state correctly.
        Issue #811, fixed in revision r12857.
        """
        return self._reentrantStreamingProducerTest('write')


    def test_reentrantStreamingProducerUsingWriteSequence(self):
        """
        Like L{test_reentrantStreamingProducerUsingWrite}, but for calls to
        C{writeSequence}.

        C{writeSequence} is B{not} part of L{IConsumer}, however
        C{abstract.FileDescriptor} has supported consumery behavior in response
        to calls to C{writeSequence} forever.
        """
        return self._reentrantStreamingProducerTest('writeSequence')



class PortStringificationTests(unittest.TestCase):
    if interfaces.IReactorTCP(reactor, None) is not None:
        def testTCP(self):
            p = reactor.listenTCP(0, protocol.ServerFactory())
            portNo = p.getHost().port
            self.assertNotEqual(str(p).find(str(portNo)), -1,
                                "%d not found in %s" % (portNo, p))
            return p.stopListening()

    if interfaces.IReactorUDP(reactor, None) is not None:
        def testUDP(self):
            p = reactor.listenUDP(0, protocol.DatagramProtocol())
            portNo = p.getHost().port
            self.assertNotEqual(str(p).find(str(portNo)), -1,
                                "%d not found in %s" % (portNo, p))
            return p.stopListening()

    if interfaces.IReactorSSL(reactor, None) is not None and ssl:
        def testSSL(self, ssl=ssl):
            pem = util.sibpath(__file__, 'server.pem')
            p = reactor.listenSSL(0, protocol.ServerFactory(), ssl.DefaultOpenSSLContextFactory(pem, pem))
            portNo = p.getHost().port
            self.assertNotEqual(str(p).find(str(portNo)), -1,
                                "%d not found in %s" % (portNo, p))
            return p.stopListening()

        if _PY3:
            testSSL.skip = ("Re-enable once the Python 3 SSL port is done.")
