from twisted.trial import unittest

from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.defer import deferred_f_from_coro_f


async def async_gen():
    for i in range(3):
        yield i


class AsyncGeneratorTest(unittest.TestCase):

    @deferred_f_from_coro_f
    async def test_as_async_generator_simple(self):
        gen = (i for i in range(3))
        results = []
        async for i in as_async_generator(gen):
            results.append(i)
        self.assertEqual(results, [0, 1, 2])

    @deferred_f_from_coro_f
    async def test_as_async_generator_list(self):
        L = [i for i in range(3)]
        results = []
        async for i in as_async_generator(L):
            results.append(i)
        self.assertEqual(results, [0, 1, 2])

    @deferred_f_from_coro_f
    async def test_as_async_generator_async(self):
        results = []
        async for i in as_async_generator(async_gen()):
            results.append(i)
        self.assertEqual(results, [0, 1, 2])

    @deferred_f_from_coro_f
    async def test_collect_asyncgen(self):
        results = await collect_asyncgen(async_gen())
        self.assertEqual(results, [0, 1, 2])
