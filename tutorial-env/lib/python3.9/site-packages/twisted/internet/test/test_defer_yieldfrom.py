# -*- test-case-name: twisted.internet.test.test_defer_yieldfrom -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for C{yield from} support in Deferreds.
"""

import types

from twisted.internet.defer import Deferred, ensureDeferred, fail, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase


class YieldFromTests(TestCase):
    """
    Tests for using Deferreds in conjunction with PEP-380.
    """

    def test_ensureDeferred(self):
        """
        L{ensureDeferred} will turn a coroutine into a L{Deferred}.
        """

        def run():
            d = succeed("foo")
            res = yield from d
            return res

        # It's a generator...
        r = run()
        self.assertIsInstance(r, types.GeneratorType)

        # Now it's a Deferred.
        d = ensureDeferred(r)
        self.assertIsInstance(d, Deferred)

        # The Deferred has the result we want.
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")

    def test_DeferredfromCoroutine(self):
        """
        L{Deferred.fromCoroutine} will turn a coroutine into a L{Deferred}.
        """

        def run():
            d = succeed("bar")
            yield from d
            res = yield from run2()
            return res

        def run2():
            d = succeed("foo")
            res = yield from d
            return res

        # It's a generator...
        r = run()
        self.assertIsInstance(r, types.GeneratorType)

        # Now it's a Deferred.
        d = Deferred.fromCoroutine(r)
        self.assertIsInstance(d, Deferred)

        # The Deferred has the result we want.
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")

    def test_basic(self):
        """
        L{Deferred.fromCoroutine} allows a function to C{yield from} a
        L{Deferred}.
        """

        def run():
            d = succeed("foo")
            res = yield from d
            return res

        d = Deferred.fromCoroutine(run())
        res = self.successResultOf(d)
        self.assertEqual(res, "foo")

    def test_exception(self):
        """
        An exception in a generator scheduled with L{Deferred.fromCoroutine}
        will cause the returned L{Deferred} to fire with a failure.
        """

        def run():
            d = succeed("foo")
            yield from d
            raise ValueError("Oh no!")

        d = Deferred.fromCoroutine(run())
        res = self.failureResultOf(d)
        self.assertEqual(type(res.value), ValueError)
        self.assertEqual(res.value.args, ("Oh no!",))

    def test_twoDeep(self):
        """
        An exception in a generator scheduled with L{Deferred.fromCoroutine}
        will cause the returned L{Deferred} to fire with a failure.
        """
        reactor = Clock()
        sections = []

        def runone():
            sections.append(2)
            d = Deferred()
            reactor.callLater(1, d.callback, None)
            yield from d
            sections.append(3)
            return "Yay!"

        def run():
            sections.append(1)
            result = yield from runone()
            sections.append(4)
            d = Deferred()
            reactor.callLater(1, d.callback, None)
            yield from d
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
        Yielding from an already failed Deferred will raise the exception.
        """

        def test():
            try:
                yield from fail(ValueError("Boom"))
            except ValueError as e:
                self.assertEqual(e.args, ("Boom",))
                return 1
            return 0

        res = self.successResultOf(Deferred.fromCoroutine(test()))
        self.assertEqual(res, 1)

    def test_chained(self):
        """
        Yielding from a paused & chained Deferred will give the result when it
        has one.
        """
        reactor = Clock()

        def test():
            d = Deferred()
            d2 = Deferred()
            d.addCallback(lambda ignored: d2)

            d.callback(None)
            reactor.callLater(0, d2.callback, "bye")
            res = yield from d
            return res

        d = Deferred.fromCoroutine(test())
        reactor.advance(0.1)

        res = self.successResultOf(d)
        self.assertEqual(res, "bye")
