import warnings
from functools import wraps

from twisted.internet import defer, threads


def deprecated(use_instead=None):
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""

    def wrapped(func):
        @wraps(func)
        def new_func(*args, **kwargs):
            message = "Call to deprecated function %s." % func.__name__
            if use_instead:
                message += " Use %s instead." % use_instead
            warnings.warn(message, category=DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        return new_func
    return wrapped

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
