# -*- test-case-name: twisted.internet.test.test_defer_await -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for C{await} support in Deferreds.
"""

import types

from twisted.internet.defer import (
    Deferred,
    ensureDeferred,
    fail,
    maybeDeferred,
    succeed,
)
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase


class SampleException(Exception):
    """
    A specific sample exception for testing.
    """


class AwaitTests(TestCase):
    """
    Tests for using Deferreds in conjunction with PEP-492.
    """

    def test_awaitReturnsIterable(self):
        """
        C{Deferred.__await__} returns an iterable.
        """
        d = Deferred()
        awaitedDeferred = d.__await__()
        self.assertEqual(awaitedDeferred, iter(awaitedDeferred))

    def test_deferredFromCoroutine(self):
        """
        L{Deferred.fromCoroutine} will turn a coroutine into a L{Deferred}.
        """

        async def run():
            d = succeed("bar")
            await d
            res = await run2()
            return res

        async def run2():
            d = succeed("foo")
            res = await d
            return res

        # It's a coroutine...
        r = run()
        self.assertIsInstance(r, types.CoroutineType)

        # Now it's a Deferred.
        d = Deferred.fromCoroutine(r)
        self.assertIsInstance(d, Deferred)

        # The Deferred has the result we want.
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")

    def test_basic(self):
        """
        L{Deferred.fromCoroutine} allows a function to C{await} on a
        L{Deferred}.
        """

        async def run():
            d = succeed("foo")
            res = await d
            return res

        d = Deferred.fromCoroutine(run())
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")

    def test_basicEnsureDeferred(self):
        """
        L{ensureDeferred} allows a function to C{await} on a L{Deferred}.
        """

        async def run():
            d = succeed("foo")
            res = await d
            return res

        d = ensureDeferred(run())
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")

    def test_exception(self):
        """
        An exception in a coroutine scheduled with L{Deferred.fromCoroutine}
        will cause the returned L{Deferred} to fire with a failure.
        """

        async def run():
            d = succeed("foo")
            await d
            raise ValueError("Oh no!")

        d = Deferred.fromCoroutine(run())
        res = self.failureResultOf(d)
        self.assertEqual(type(res.value), ValueError)
        self.assertEqual(res.value.args, ("Oh no!",))

    def test_synchronousDeferredFailureTraceback(self):
        """
        When a Deferred is awaited upon that has already failed with a Failure
        that has a traceback, both the place that the synchronous traceback
        comes from and the awaiting line are shown in the traceback.
        """

        def raises():
            raise SampleException()

        it = maybeDeferred(raises)

        async def doomed():
            return await it

        failure = self.failureResultOf(Deferred.fromCoroutine(doomed()))

        self.assertIn(", in doomed\n", failure.getTraceback())
        self.assertIn(", in raises\n", failure.getTraceback())

    def test_asyncDeferredFailureTraceback(self):
        """
        When a Deferred is awaited upon that later fails with a Failure that
        has a traceback, both the place that the synchronous traceback comes
        from and the awaiting line are shown in the traceback.
        """

        def returnsFailure():
            try:
                raise SampleException()
            except SampleException:
                return Failure()

        it = Deferred()

        async def doomed():
            return await it

        started = Deferred.fromCoroutine(doomed())
        self.assertNoResult(started)
        it.errback(returnsFailure())
        failure = self.failureResultOf(started)
        self.assertIn(", in doomed\n", failure.getTraceback())
        self.assertIn(", in returnsFailure\n", failure.getTraceback())

    def test_twoDeep(self):
        """
        A coroutine scheduled with L{Deferred.fromCoroutine} that awaits a
        L{Deferred} suspends its execution until the inner L{Deferred} fires.
        """
        reactor = Clock()
        sections = []

        async def runone():
            sections.append(2)
            d = Deferred()
            reactor.callLater(1, d.callback, 2)
            await d
            sections.append(3)
            return "Yay!"

        async def run():
            sections.append(1)
            result = await runone()
            sections.append(4)
            d = Deferred()
            reactor.callLater(1, d.callback, 1)
            await d
            sections.append(5)
            return result

        d = Deferred.fromCoroutine(run())

        reactor.advance(0.9)
        self.assertEqual(sections, [1, 2])

        reactor.advance(0.1)
        self.assertEqual(sections, [1, 2, 3, 4])

        reactor.advance(0.9)
        self.assertEqual(sections, [1, 2, 3, 4])

        reactor.advance(0.1)
        self.assertEqual(sections, [1, 2, 3, 4, 5])

        res = self.successResultOf(d)
        self.assertEqual(res, "Yay!")

    def test_reraise(self):
        """
        Awaiting an already failed Deferred will raise the exception.
        """

        async def test():
            try:
                await fail(ValueError("Boom"))
            except ValueError as e:
                self.assertEqual(e.args, ("Boom",))
                return 1
            return 0

        res = self.successResultOf(Deferred.fromCoroutine(test()))
        self.assertEqual(res, 1)

    def test_chained(self):
        """
        Awaiting a paused & chained Deferred will give the result when it has
        one.
        """
        reactor = Clock()

        async def test():
            d = Deferred()
            d2 = Deferred()
            d.addCallback(lambda ignored: d2)

            d.callback(None)
            reactor.callLater(0, d2.callback, "bye")
            return await d

        d = Deferred.fromCoroutine(test())
        reactor.advance(0.1)

        res = self.successResultOf(d)
        self.assertEqual(res, "bye")
