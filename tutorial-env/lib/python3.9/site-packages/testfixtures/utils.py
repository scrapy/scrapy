import sys
from functools import wraps
from textwrap import dedent

from inspect import getfullargspec
from typing import Callable, Sequence, Any

from . import singleton

DEFAULT = singleton('DEFAULT')
defaults = [DEFAULT]


try:
    from .mock import DEFAULT
except ImportError:  # pragma: no cover
    pass
else:
    defaults.append(DEFAULT)


def generator(*args):
    """
    A utility function for creating a generator that will yield the
    supplied arguments.
    """
    for i in args:
        yield i


class Wrapping:

    attribute_name = None
    new = DEFAULT

    def __init__(self, before: Callable[[], None], after: Callable[[], None]):
        self.before, self.after = before, after

    def __enter__(self):
        return self.before()

    def __exit__(self, exc_type=None, exc_val=None, exc_tb=None):
        if self.after is not None:
            self.after()


def wrap(before: Callable[[], Any], after: Callable[[], Any] = None):
    """
    A decorator that causes the supplied callables to be called before
    or after the wrapped callable, as appropriate.
    """

    wrapping = Wrapping(before, after)

    def wrapper(func):
        if hasattr(func, 'patchings'):
            func.patchings.append(wrapping)
            return func

        @wraps(func)
        def patched(*args, **keywargs):
            extra_args = []
            entered_patchers = []

            to_add = len(getfullargspec(func).args[len(args):])
            added = 0

            exc_info = (None, None, None)
            try:
                for patching in patched.patchings:
                    arg = patching.__enter__()
                    entered_patchers.append(patching)
                    if patching.attribute_name is not None:
                        keywargs.update(arg)
                    elif patching.new in defaults and added < to_add:
                        extra_args.append(arg)
                        added += 1

                args += tuple(extra_args)
                return func(*args, **keywargs)
            except:
                # Pass the exception to __exit__
                exc_info = sys.exc_info()
                # re-raise the exception
                raise
            finally:
                for patching in reversed(entered_patchers):
                    patching.__exit__(*exc_info)

        patched.patchings = [wrapping]
        return patched

    return wrapper


def extend_docstring(docstring: str, objs: Sequence):
    for obj in objs:
        obj.__doc__ = dedent(obj.__doc__) + docstring


def indent(text: str, indent_size: int = 2):
    indented = []
    for do_indent, line in enumerate(text.splitlines(True)):
        if do_indent:
            line = ' '*indent_size + line
        indented.append(line)
    return ''.join(indented)
