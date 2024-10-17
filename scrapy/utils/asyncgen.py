from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterable, Iterable
from typing import TypeVar

_T = TypeVar("_T")


async def collect_asyncgen(result: AsyncIterable[_T]) -> list[_T]:
    results = []
    async for x in result:
        results.append(x)
    return results


async def as_async_generator(
    it: Iterable[_T] | AsyncIterable[_T],
) -> AsyncGenerator[_T]:
    """Wraps an iterable (sync or async) into an async generator."""
    if isinstance(it, AsyncIterable):
        async for r in it:
            yield r
    else:
        for r in it:
            yield r
