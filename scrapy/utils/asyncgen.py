from typing import AsyncGenerator, AsyncIterable, Iterable, Union


async def collect_asyncgen(result: AsyncIterable) -> list:
    results = []
    async for x in result:
        results.append(x)
    return results


async def as_async_generator(it: Union[Iterable, AsyncIterable]) -> AsyncGenerator:
    """ Wraps an iterable (sync or async) into an async generator. """
    if isinstance(it, AsyncIterable):
        async for r in it:
            yield r
    else:
        for r in it:
            yield r
