import warnings
from functools import wraps

from twisted.internet import defer, threads

from scrapy.exceptions import ScrapyDeprecationWarning


def deprecated(use_instead=None):
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""

    def deco(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
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


def defers(func):
    """Decorator to make sure a function always returns a deferred"""

    @wraps(func)
    def wrapped(*a, **kw):
        return defer.maybeDeferred(func, *a, **kw)

    return wrapped


def inthread(func):
    """Decorator to call a function in a thread and return a deferred with the
    result
    """

    @wraps(func)
    def wrapped(*a, **kw):
        return threads.deferToThread(func, *a, **kw)

    return wrapped
