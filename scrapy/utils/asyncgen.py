"""
Helpers using Python 3.6+ async generator syntax (ignore SyntaxError on import).
"""
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


async def process_async_iterable_helper(it, in_predicate=None, out_predicate=None, processor=None):
    async for o in it:
        if in_predicate and not in_predicate(o):
            continue
        if processor is not None:
            o = processor(o)
        if out_predicate and not out_predicate(o):
            continue
        yield o
