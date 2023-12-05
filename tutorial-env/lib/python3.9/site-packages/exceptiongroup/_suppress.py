import sys
from contextlib import AbstractContextManager

if sys.version_info < (3, 11):
    from ._exceptions import BaseExceptionGroup


class suppress(AbstractContextManager):
    """Backport of :class:`contextlib.suppress` from Python 3.12.1."""

    def __init__(self, *exceptions):
        self._exceptions = exceptions

    def __enter__(self):
        pass

    def __exit__(self, exctype, excinst, exctb):
        # Unlike isinstance and issubclass, CPython exception handling
        # currently only looks at the concrete type hierarchy (ignoring
        # the instance and subclass checking hooks). While Guido considers
        # that a bug rather than a feature, it's a fairly hard one to fix
        # due to various internal implementation details. suppress provides
        # the simpler issubclass based semantics, rather than trying to
        # exactly reproduce the limitations of the CPython interpreter.
        #
        # See http://bugs.python.org/issue12029 for more details
        if exctype is None:
            return

        if issubclass(exctype, self._exceptions):
            return True

        if issubclass(exctype, BaseExceptionGroup):
            match, rest = excinst.split(self._exceptions)
            if rest is None:
                return True

            raise rest

        return False
