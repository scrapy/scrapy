"""
Copy/paste from scrapy source at the moment, to ensure tests are working.
Refactoring to come later
"""
import inspect
from functools import partial

from itemadapter import is_item

_ITERABLE_SINGLE_VALUES = str, bytes


def arg_to_iter(arg):
    """Convert an argument to an iterable. The argument can be a None, single
    value, or an iterable.

    Exception: if arg is a dict, [arg] will be returned
    """
    if arg is None:
        return []
    elif (
        hasattr(arg, "__iter__")
        and not isinstance(arg, _ITERABLE_SINGLE_VALUES)
        and not is_item(arg)
    ):
        return arg
    else:
        return [arg]


def get_func_args(func, stripself=False):
    """Return the argument name list of a callable object"""
    if not callable(func):
        raise TypeError(f"func must be callable, got {type(func).__name__!r}")

    args = []
    try:
        sig = inspect.signature(func)
    except ValueError:
        return args

    if isinstance(func, partial):
        partial_args = func.args
        partial_kw = func.keywords

        for name, param in sig.parameters.items():
            if param.name in partial_args:
                continue
            if partial_kw and param.name in partial_kw:
                continue
            args.append(name)
    else:
        for name in sig.parameters.keys():
            args.append(name)

    if stripself and args and args[0] == "self":
        args = args[1:]
    return args
