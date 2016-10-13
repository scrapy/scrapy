from __future__ import absolute_import

import inspect

import six


def func_accepts_kwargs(func):
        # Not all callables are inspectable with getargspec, so we'll
        # try a couple different ways.
        # First check if object is callable
        if not callable(func):
            raise TypeError('{!r} is not a callable object'.format(func))
        try:
            if six.PY2:
                argspec = inspect.getargspec(func)
            else:
                argspec = inspect.getfullargspec(func)
        except TypeError:
            try:
                if six.PY2:
                    argspec = inspect.getargspec(func.__call__)
                else:
                    argspec = inspect.getfullargspec(func.__call__)
            except (TypeError, AttributeError):
                # We fall back to assuming the callable does accept kwargs,
                # since we don't want to prevent registration of valid but
                # weird receivers.
                argspec = None
        return not argspec or argspec[2] is not None
