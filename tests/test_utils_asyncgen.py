from twisted.trial import unittest

from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.defer import deferred_f_from_coro_f


class TestAsyncgenUtils(unittest.TestCase):
    @deferred_f_from_coro_f
    async def test_as_async_generator(self):
        ag = as_async_generator(range(42))
        results = [i async for i in ag]
        assert results == list(range(42))

    @deferred_f_from_coro_f
    async def test_collect_asyncgen(self):
        ag = as_async_generator(range(42))
        results = await collect_asyncgen(ag)
        assert results == list(range(42))
