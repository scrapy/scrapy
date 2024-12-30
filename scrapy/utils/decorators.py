from __future__ import annotations

import warnings
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.threads import deferToThread

from scrapy.exceptions import ScrapyDeprecationWarning

if TYPE_CHECKING:
    from collections.abc import Callable

    # typing.ParamSpec requires Python 3.10
    from typing_extensions import ParamSpec

    _P = ParamSpec("_P")


_T = TypeVar("_T")


def deprecated(
    use_instead: Any = None,
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""

    def deco(func: Callable[_P, _T]) -> Callable[_P, _T]:
        @wraps(func)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> Any:
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


def defers(func: Callable[_P, _T]) -> Callable[_P, Deferred[_T]]:
    """Decorator to make sure a function always returns a deferred"""

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
