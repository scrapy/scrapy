import sys

from pytest import mark
from twisted.trial import unittest

from scrapy.utils.defer import deferred_f_from_coro_f


@mark.skipif(sys.version_info < (3, 6), reason="Async generators require Python 3.6 or higher")
class AsyncGeneratorTest(unittest.TestCase):

    @deferred_f_from_coro_f
    async def test_as_async_generator_simple(self):
        from scrapy.utils.asyncgen import as_async_generator
        gen = (i for i in range(3))
        results = []
        async for i in as_async_generator(gen):
            results.append(i)
        self.assertEqual(results, [0, 1, 2])

    @deferred_f_from_coro_f
    async def test_as_async_generator_list(self):
        from scrapy.utils.asyncgen import as_async_generator
        L = [i for i in range(3)]
        results = []
        async for i in as_async_generator(L):
            results.append(i)
        self.assertEqual(results, [0, 1, 2])

    @deferred_f_from_coro_f
    async def test_as_async_generator_async(self):
        from scrapy.utils.asyncgen import as_async_generator
        from tests.py36._test_utils_asyncgen import async_gen
        results = []
        async for i in as_async_generator(async_gen()):
            results.append(i)
        self.assertEqual(results, [0, 1, 2])

    @deferred_f_from_coro_f
    async def test_collect_asyncgen(self):
        from scrapy.utils.asyncgen import collect_asyncgen
        from tests.py36._test_utils_asyncgen import async_gen
        results = await collect_asyncgen(async_gen())
        self.assertEqual(results, [0, 1, 2])
