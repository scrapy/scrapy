from typing import AsyncGenerator, AsyncIterable, Iterable, List, TypeVar, Union

_T = TypeVar("_T")


async def collect_asyncgen(result: AsyncIterable[_T]) -> List[_T]:
    results = []
    async for x in result:
        results.append(x)
    return results


async def as_async_generator(
    it: Union[Iterable[_T], AsyncIterable[_T]]
) -> AsyncGenerator[_T, None]:
    """Wraps an iterable (sync or async) into an async generator."""
    if isinstance(it, AsyncIterable):
        async for r in it:
            yield r
    else:
        for r in it:
            yield r
