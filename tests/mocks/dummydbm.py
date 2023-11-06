"""DBM-like dummy module"""
import collections
from typing import Any, DefaultDict


class DummyDB(dict):
    """Provide dummy DBM-like interface."""

    def close(self):
        pass


error = KeyError


_DATABASES: DefaultDict[Any, DummyDB] = collections.defaultdict(DummyDB)


def open(file, flag="r", mode=0o666):
    """Open or create a dummy database compatible.

    Arguments ``flag`` and ``mode`` are ignored.
    """
    # return same instance for same file argument
    return _DATABASES[file]
