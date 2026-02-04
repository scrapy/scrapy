from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from tests.utils.decorators import coroutine_test


class TestAsyncgenUtils:
    @coroutine_test
    async def test_as_async_generator(self):
        ag = as_async_generator(range(42))
        results = [i async for i in ag]
        assert results == list(range(42))

    @coroutine_test
    async def test_collect_asyncgen(self):
        ag = as_async_generator(range(42))
        results = await collect_asyncgen(ag)
        assert results == list(range(42))
