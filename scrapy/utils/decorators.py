import warnings
from functools import wraps
from typing import Any, Callable

from twisted.internet import defer, threads
from twisted.internet.defer import Deferred

from scrapy.exceptions import ScrapyDeprecationWarning


def deprecated(use_instead: Any = None) -> Callable:
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""

    def deco(func: Callable) -> Callable:
        @wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
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


def defers(func: Callable) -> Callable[..., Deferred]:
    """Decorator to make sure a function always returns a deferred"""

    @wraps(func)
    def wrapped(*a: Any, **kw: Any) -> Deferred:
        return defer.maybeDeferred(func, *a, **kw)

    return wrapped


def inthread(func: Callable) -> Callable[..., Deferred]:
    """Decorator to call a function in a thread and return a deferred with the
    result
    """

    @wraps(func)
    def wrapped(*a: Any, **kw: Any) -> Deferred:
        return threads.deferToThread(func, *a, **kw)

    return wrapped
