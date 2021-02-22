from pytest import mark
from twisted.trial import unittest
from twisted.internet import reactor, defer
from twisted.python.failure import Failure

from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    iter_errback,
    mustbe_deferred,
    process_chain,
    process_chain_both,
    process_parallel,
)


class MustbeDeferredTest(unittest.TestCase):
    def test_success_function(self):
        steps = []

        def _append(v):
            steps.append(v)
            return steps

        dfd = mustbe_deferred(_append, 1)
        dfd.addCallback(self.assertEqual, [1, 2])  # it is [1] with maybeDeferred
        steps.append(2)  # add another value, that should be catched by assertEqual
        return dfd

    def test_unfired_deferred(self):
        steps = []

        def _append(v):
            steps.append(v)
            dfd = defer.Deferred()
            reactor.callLater(0, dfd.callback, steps)
            return dfd

        dfd = mustbe_deferred(_append, 1)
        dfd.addCallback(self.assertEqual, [1, 2])  # it is [1] with maybeDeferred
        steps.append(2)  # add another value, that should be catched by assertEqual
        return dfd


def cb1(value, arg1, arg2):
    return f"(cb1 {value} {arg1} {arg2})"


def cb2(value, arg1, arg2):
    return defer.succeed(f"(cb2 {value} {arg1} {arg2})")


def cb3(value, arg1, arg2):
    return f"(cb3 {value} {arg1} {arg2})"


def cb_fail(value, arg1, arg2):
    return Failure(TypeError())


def eb1(failure, arg1, arg2):
    return f"(eb1 {failure.value.__class__.__name__} {arg1} {arg2})"


class DeferUtilsTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_process_chain(self):
        x = yield process_chain([cb1, cb2, cb3], 'res', 'v1', 'v2')
        self.assertEqual(x, "(cb3 (cb2 (cb1 res v1 v2) v1 v2) v1 v2)")

        gotexc = False
        try:
            yield process_chain([cb1, cb_fail, cb3], 'res', 'v1', 'v2')
        except TypeError:
            gotexc = True
        self.assertTrue(gotexc)

    @defer.inlineCallbacks
    def test_process_chain_both(self):
        x = yield process_chain_both([cb_fail, cb2, cb3], [None, eb1, None], 'res', 'v1', 'v2')
        self.assertEqual(x, "(cb3 (eb1 TypeError v1 v2) v1 v2)")

        fail = Failure(ZeroDivisionError())
        x = yield process_chain_both([eb1, cb2, cb3], [eb1, None, None], fail, 'v1', 'v2')
        self.assertEqual(x, "(cb3 (cb2 (eb1 ZeroDivisionError v1 v2) v1 v2) v1 v2)")

    @defer.inlineCallbacks
    def test_process_parallel(self):
        x = yield process_parallel([cb1, cb2, cb3], 'res', 'v1', 'v2')
        self.assertEqual(x, ['(cb1 res v1 v2)', '(cb2 res v1 v2)', '(cb3 res v1 v2)'])

    def test_process_parallel_failure(self):
        d = process_parallel([cb1, cb_fail, cb3], 'res', 'v1', 'v2')
        self.failUnlessFailure(d, TypeError)
        return d


class IterErrbackTest(unittest.TestCase):

    def test_iter_errback_good(self):
        def itergood():
            for x in range(10):
                yield x

        errors = []
        out = list(iter_errback(itergood(), errors.append))
        self.assertEqual(out, list(range(10)))
        self.assertFalse(errors)

    def test_iter_errback_bad(self):
        def iterbad():
            for x in range(10):
                if x == 5:
                    1 / 0
                yield x

        errors = []
        out = list(iter_errback(iterbad(), errors.append))
        self.assertEqual(out, [0, 1, 2, 3, 4])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0].value, ZeroDivisionError)


class AsyncDefTestsuiteTest(unittest.TestCase):
    @deferred_f_from_coro_f
    async def test_deferred_f_from_coro_f(self):
        pass

    @deferred_f_from_coro_f
    async def test_deferred_f_from_coro_f_generator(self):
        yield

    @mark.xfail(reason="Checks that the test is actually executed", strict=True)
    @deferred_f_from_coro_f
    async def test_deferred_f_from_coro_f_xfail(self):
        raise Exception("This is expected to be raised")
