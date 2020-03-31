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
            message = "Call to deprecated function %s." % func.__name__
            if use_instead:
                message += " Use %s instead." % use_instead
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


try:
    from dataclasses import fields as dataclass_fields
except ImportError:
    pass
else:
    def subscriptable_dataclass(cls):
        """
        Allow dictionary-like access on dataclass instances

        >>> from dataclasses import dataclass
        >>> from scrapy.utils.decorators import subscriptable_dataclass
        >>> @subscriptable_dataclass
        ... @dataclass
        ... class InventoryItem:
        ...     name: str
        ...     price: int
        ...
        >>> d = InventoryItem(name="foobar", price=10)
        >>> d["name"]
        'foobar'
        >>> d["price"] = 5
        >>> d
        InventoryItem(name='foobar', price=5)
        """

        def __getitem__(self, key):
            field_names = [f.name for f in dataclass_fields(self)]
            if key in field_names:
                return getattr(self, key)
            raise KeyError(key)

        def __setitem__(self, key, value):
            field_names = [f.name for f in dataclass_fields(self)]
            if key in field_names:
                setattr(self, key, value)
            else:
                raise KeyError("%s does not support field: %s" % (self.__class__.__name__, key))

        setattr(cls, "__getitem__", __getitem__)
        setattr(cls, "__setitem__", __setitem__)
        return cls
