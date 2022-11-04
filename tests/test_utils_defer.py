import random

from pytest import mark
from twisted.trial import unittest
from twisted.internet import reactor, defer
from twisted.python.failure import Failure

from scrapy.utils.asyncgen import collect_asyncgen, as_async_generator
from scrapy.utils.defer import (
    aiter_errback,
    deferred_f_from_coro_f,
    iter_errback,
    maybe_deferred_to_future,
    mustbe_deferred,
    parallel_async,
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
        steps.append(2)  # add another value, that should be caught by assertEqual
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
        steps.append(2)  # add another value, that should be caught by assertEqual
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


class AiterErrbackTest(unittest.TestCase):

    @deferred_f_from_coro_f
    async def test_aiter_errback_good(self):
        async def itergood():
            for x in range(10):
                yield x

        errors = []
        out = await collect_asyncgen(aiter_errback(itergood(), errors.append))
        self.assertEqual(out, list(range(10)))
        self.assertFalse(errors)

    @deferred_f_from_coro_f
    async def test_iter_errback_bad(self):
        async def iterbad():
            for x in range(10):
                if x == 5:
                    1 / 0
                yield x

        errors = []
        out = await collect_asyncgen(aiter_errback(iterbad(), errors.append))
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


class AsyncCooperatorTest(unittest.TestCase):
    """ This tests _AsyncCooperatorAdapter by testing parallel_async which is its only usage.

    parallel_async is called with the results of a callback (so an iterable of items, requests and None,
    with arbitrary delays between values), and it uses Scraper._process_spidermw_output as the callable
    (so a callable that returns a Deferred for an item, which will fire after pipelines process it, and
    None for everything else). The concurrent task count is the CONCURRENT_ITEMS setting.

    We want to test different concurrency values compared to the iterable length.
    We also want to simulate the real usage, with arbitrary delays between getting the values
    from the iterable. We also want to simulate sync and async results from the callable.
    """
    CONCURRENT_ITEMS = 50

    @staticmethod
    def callable(o, results):
        if random.random() < 0.4:
            # simulate async processing
            dfd = defer.Deferred()
            dfd.addCallback(lambda _: results.append(o))
            delay = random.random() / 8
            reactor.callLater(delay, dfd.callback, None)
            return dfd
        else:
            # simulate trivial sync processing
            results.append(o)

    @staticmethod
    def get_async_iterable(length):
        # simulate a simple callback without delays between results
        return as_async_generator(range(length))

    @staticmethod
    async def get_async_iterable_with_delays(length):
        # simulate a callback with delays between some of the results
        for i in range(length):
            if random.random() < 0.1:
                dfd = defer.Deferred()
                delay = random.random() / 20
                reactor.callLater(delay, dfd.callback, None)
                await maybe_deferred_to_future(dfd)
            yield i

    @defer.inlineCallbacks
    def test_simple(self):
        for length in [20, 50, 100]:
            results = []
            ait = self.get_async_iterable(length)
            dl = parallel_async(ait, self.CONCURRENT_ITEMS, self.callable, results)
            yield dl
            self.assertEqual(list(range(length)), sorted(results))

    @defer.inlineCallbacks
    def test_delays(self):
        for length in [20, 50, 100]:
            results = []
            ait = self.get_async_iterable_with_delays(length)
            dl = parallel_async(ait, self.CONCURRENT_ITEMS, self.callable, results)
            yield dl
            self.assertEqual(list(range(length)), sorted(results))
