from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec

import pytest
from twisted.internet.defer import Deferred
from twisted.internet.defer import inlineCallbacks as inlineCallbacks_orig

from scrapy.utils.defer import deferred_from_coro

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator


_P = ParamSpec("_P")


def inlineCallbacks(
    f: Callable[_P, Generator[Deferred[Any], Any, None]],
) -> Callable[_P, Deferred[None]]:
    """Like :func:`twisted.internet.defer.inlineCallbacks`, but marks the
    decorated function with ``@pytest.mark.requires_reactor``."""

    @pytest.mark.requires_reactor
    @wraps(f)
    @inlineCallbacks_orig
    def wrapper(
        *args: _P.args, **kwargs: _P.kwargs
    ) -> Generator[Deferred[Any], Any, None]:
        return f(*args, **kwargs)

    return wrapper


def deferred_f_from_coro_f(
    coro_f: Callable[_P, Awaitable[None]],
) -> Callable[_P, Deferred[None]]:
    """Like :func:`scrapy.utils.defer.deferred_f_from_coro_f`, but marks the
    decorated function with ``@pytest.mark.requires_reactor``."""

    @pytest.mark.requires_reactor
    @wraps(coro_f)
    def f(*coro_args: _P.args, **coro_kwargs: _P.kwargs) -> Deferred[None]:
        return deferred_from_coro(coro_f(*coro_args, **coro_kwargs))

    return f
