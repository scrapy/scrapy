import collections


async def collect_asyncgen(result):
    results = []
    async for x in result:
        results.append(x)
    return results


async def as_async_generator(it):
    if isinstance(it, collections.abc.AsyncIterator):
        async for r in it:
            yield r
    else:
        for r in it:
            yield r
