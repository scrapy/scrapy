"""Utilities related to asyncio and its support in Scrapy."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypeVar

from scrapy.utils.asyncgen import as_async_generator
from scrapy.utils.reactor import is_asyncio_reactor_installed, is_reactor_installed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine, Iterable

    # typing.Concatenate and typing.ParamSpec require Python 3.10
    from typing_extensions import Concatenate, ParamSpec

    _P = ParamSpec("_P")

_T = TypeVar("_T")


def is_asyncio_available() -> bool:
    """Check if it's possible to call asyncio code that relies on the asyncio event loop.

    .. versionadded:: VERSION

    Currently this function is identical to
    :func:`scrapy.utils.reactor.is_asyncio_reactor_installed`: it returns
    ``True`` if the Twisted reactor that is installed is
    :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`, returns
    ``False`` if a different reactor is installed, and raises a
    :exc:`RuntimeError` if no reactor is installed. In a future Scrapy version,
    when Scrapy supports running without a Twisted reactor, this function will
    also return ``True`` when running in that mode, so code that doesn't
    directly require a Twisted reactor should use this function instead of
    :func:`~scrapy.utils.reactor.is_asyncio_reactor_installed`.

    When this returns ``True``, an asyncio loop is installed and used by
    Scrapy. It's possible to call functions that require it, such as
    :func:`asyncio.sleep`, and await on :class:`asyncio.Future` objects in
    Scrapy-related code.

    When this returns ``False``, a non-asyncio Twisted reactor is installed.
    It's not possible to use asyncio features that require an asyncio event
    loop or await on :class:`asyncio.Future` objects in Scrapy-related code,
    but it's possible to await on :class:`~twisted.internet.defer.Deferred`
    objects.
    """
    if not is_reactor_installed():
        raise RuntimeError(
            "is_asyncio_available() called without an installed reactor."
        )

    return is_asyncio_reactor_installed()


async def _parallel_asyncio(
    iterable: Iterable[_T] | AsyncIterator[_T],
    count: int,
    callable: Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> None:
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    This function is only used in
    :meth:`scrapy.core.scraper.Scraper.handle_spider_output_async` and so it
    assumes that neither *callable* nor iterating *iterable* will raise an
    exception.
    """
    queue: asyncio.Queue[_T | None] = asyncio.Queue()

    async def worker() -> None:
        while True:
            item = await queue.get()
            if item is None:
                break
            try:
                await callable(item, *args, **kwargs)
            finally:
                queue.task_done()

    async def fill_queue() -> None:
        async for item in as_async_generator(iterable):
            await queue.put(item)
        for _ in range(count):
            await queue.put(None)

    fill_task = asyncio.create_task(fill_queue())
    work_tasks = [asyncio.create_task(worker()) for _ in range(count)]
    await asyncio.wait([fill_task, *work_tasks])
