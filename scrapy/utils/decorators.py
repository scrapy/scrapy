from __future__ import annotations

import inspect
import warnings
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, overload

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.threads import deferToThread

from scrapy.exceptions import ScrapyDeprecationWarning

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine


_T = TypeVar("_T")
_P = ParamSpec("_P")


def deprecated(
    use_instead: Any = None,
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""

    def deco(func: Callable[_P, _T]) -> Callable[_P, _T]:
        @wraps(func)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            message = f"Call to deprecated function {func.__name__}."
            if use_instead:
                message += f" Use {use_instead} instead."
            warnings.warn(message, category=ScrapyDeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return wrapped

    if callable(use_instead):
        deco = deco(use_instead)
        use_instead = None
    return deco


def defers(func: Callable[_P, _T]) -> Callable[_P, Deferred[_T]]:  # pragma: no cover
    """Decorator to make sure a function always returns a deferred"""
    warnings.warn(
        "@defers is deprecated, you can use maybeDeferred() directly if needed.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )

    @wraps(func)
    def wrapped(*a: _P.args, **kw: _P.kwargs) -> Deferred[_T]:
        return maybeDeferred(func, *a, **kw)

    return wrapped


def inthread(func: Callable[_P, _T]) -> Callable[_P, Deferred[_T]]:
    """Decorator to call a function in a thread and return a deferred with the
    result
    """

    @wraps(func)
    def wrapped(*a: _P.args, **kw: _P.kwargs) -> Deferred[_T]:
        return deferToThread(func, *a, **kw)

    return wrapped


@overload
def _warn_spider_arg(
    func: Callable[_P, Coroutine[Any, Any, _T]],
) -> Callable[_P, Coroutine[Any, Any, _T]]: ...


@overload
def _warn_spider_arg(
    func: Callable[_P, AsyncGenerator[_T]],
) -> Callable[_P, AsyncGenerator[_T]]: ...


@overload
def _warn_spider_arg(func: Callable[_P, _T]) -> Callable[_P, _T]: ...


def _warn_spider_arg(
    func: Callable[_P, _T],
) -> (
    Callable[_P, _T]
    | Callable[_P, Coroutine[Any, Any, _T]]
    | Callable[_P, AsyncGenerator[_T]]
):
    """Decorator to warn if a ``spider`` argument is passed to a function."""

    sig = inspect.signature(func)

    def check_args(*args: _P.args, **kwargs: _P.kwargs) -> None:
        bound = sig.bind(*args, **kwargs)
        if "spider" in bound.arguments:
            warnings.warn(
                f"Passing a 'spider' argument to {func.__qualname__}() is deprecated and "
                "the argument will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=3,
            )

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_inner(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            check_args(*args, **kwargs)
            return await func(*args, **kwargs)

        return async_inner

    if inspect.isasyncgenfunction(func):

        @wraps(func)
        async def asyncgen_inner(
            *args: _P.args, **kwargs: _P.kwargs
        ) -> AsyncGenerator[_T]:
            check_args(*args, **kwargs)
            async for item in func(*args, **kwargs):
                yield item

        return asyncgen_inner

    @wraps(func)
    def sync_inner(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        check_args(*args, **kwargs)
        return func(*args, **kwargs)

    return sync_inner
