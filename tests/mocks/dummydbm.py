"""DBM-like dummy module"""
import collections


class DummyDB(dict):
    """Provide dummy DBM-like interface."""
    def close(self):
        pass


error = KeyError


_DATABASES = collections.defaultdict(DummyDB)


def open(file, flag='r', mode=0o666):
    """Open or create a dummy database compatible.

    Arguments ``flag`` and ``mode`` are ignored.
    """
    # return same instance for same file argument
    return _DATABASES[file]
