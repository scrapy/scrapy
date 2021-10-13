from twisted.internet.defer import Deferred
from twisted.trial import unittest

from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen, _process_iterable_universal
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.test import get_web_client_agent_req


class AsyncgenUtilsTest(unittest.TestCase):
    @deferred_f_from_coro_f
    async def test_as_async_generator(self):
        ag = as_async_generator(range(42))
        results = []
        async for i in ag:
            results.append(i)
        self.assertEqual(results, list(range(42)))

    @deferred_f_from_coro_f
    async def test_collect_asyncgen(self):
        ag = as_async_generator(range(42))
        results = await collect_asyncgen(ag)
        self.assertEqual(results, list(range(42)))


@_process_iterable_universal
async def process_iterable(iterable):
    async for i in iterable:
        yield i * 2


@_process_iterable_universal
async def process_iterable_awaiting(iterable):
    async for i in iterable:
        yield i * 2
        d = Deferred()
        from twisted.internet import reactor
        reactor.callLater(0, d.callback, 42)
        await d


class ProcessIterableUniversalTest(unittest.TestCase):

    def test_normal(self):
        iterable = iter([1, 2, 3])
        results = list(process_iterable(iterable))
        self.assertEqual(results, [2, 4, 6])

    @deferred_f_from_coro_f
    async def test_async(self):
        iterable = as_async_generator([1, 2, 3])
        results = await collect_asyncgen(process_iterable(iterable))
        self.assertEqual(results, [2, 4, 6])

    @deferred_f_from_coro_f
    async def test_blocking(self):
        iterable = [1, 2, 3]
        with self.assertRaisesRegex(RuntimeError, "Synchronously-called function"):
            list(process_iterable_awaiting(iterable))

    def test_invalid_iterable(self):
        with self.assertRaisesRegex(TypeError, "Wrong iterable type"):
            process_iterable(None)

    @deferred_f_from_coro_f
    async def test_invalid_process(self):
        @_process_iterable_universal
        def process_iterable_invalid(iterable):
            pass

        with self.assertRaisesRegex(ValueError, "process_async returned wrong type"):
            list(process_iterable_invalid([]))
