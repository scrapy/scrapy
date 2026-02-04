from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec

import pytest
from twisted.internet.defer import Deferred, inlineCallbacks

from scrapy.utils.defer import deferred_from_coro, deferred_to_future
from scrapy.utils.reactor import is_reactor_installed

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator


_P = ParamSpec("_P")


def inline_callbacks_test(
    f: Callable[_P, Generator[Deferred[Any], Any, None]],
) -> Callable[_P, Awaitable[None]]:
    """Mark a test function written in a :func:`twisted.internet.defer.inlineCallbacks` style.

    This calls :func:`twisted.internet.defer.inlineCallbacks` and then:

    * with ``pytest-twisted`` this returns the resulting Deferred
    * with ``pytest-asyncio`` this converts the resulting Deferred into a
      coroutine
    """

    if not is_reactor_installed():

        @pytest.mark.asyncio
        @wraps(f)
        async def wrapper_coro(*args: _P.args, **kwargs: _P.kwargs) -> None:
            await deferred_to_future(inlineCallbacks(f)(*args, **kwargs))

        return wrapper_coro

    @wraps(f)
    @inlineCallbacks
    def wrapper_dfd(
        *args: _P.args, **kwargs: _P.kwargs
    ) -> Generator[Deferred[Any], Any, None]:
        return f(*args, **kwargs)

    return wrapper_dfd


def coroutine_test(
    coro_f: Callable[_P, Awaitable[None]],
) -> Callable[_P, Awaitable[None]]:
    """Mark a test function that returns a coroutine.

    * with ``pytest-twisted`` this converts a coroutine into a
      :class:`twisted.internet.defer.Deferred`
    * with ``pytest-asyncio`` this is a no-op
    """

    if not is_reactor_installed():
        return pytest.mark.asyncio(coro_f)

    @wraps(coro_f)
    def f(*coro_args: _P.args, **coro_kwargs: _P.kwargs) -> Deferred[None]:
        return deferred_from_coro(coro_f(*coro_args, **coro_kwargs))

    return f
