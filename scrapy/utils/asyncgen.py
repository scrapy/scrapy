from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Iterable
from typing import TypeVar

_T = TypeVar("_T")


async def collect_asyncgen(result: AsyncIterator[_T]) -> list[_T]:
    return [x async for x in result]


async def as_async_generator(
    it: Iterable[_T] | AsyncIterator[_T],
) -> AsyncGenerator[_T]:
    """Wraps an iterable (sync or async) into an async generator."""
    if isinstance(it, AsyncIterator):
        async for r in it:
            yield r
    else:
        for r in it:
            yield r
