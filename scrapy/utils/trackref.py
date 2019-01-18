"""The :mod:`scrapy.utils.trackref` module provides an API to record and report
references to live object instances.

If you want live objects for a particular class to be tracked, you only have to
subclass from object_ref (instead of object).

About performance: This library has a minimal performance impact when enabled,
and no performance penalty at all when disabled (as object_ref becomes just an
alias to object in that case).
"""

from __future__ import print_function
import weakref
from time import time
from operator import itemgetter
from collections import defaultdict
import six


NoneType = type(None)
live_refs = defaultdict(weakref.WeakKeyDictionary)


class object_ref(object):
    """Inherit from this class (instead of object) to a keep a record of live
    instances"""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        live_refs[cls][obj] = time()
        return obj


def format_live_refs(ignore=NoneType):
    """Return a tabular representation of tracked objects"""
    s = "Live References\n\n"
    now = time()
    for cls, wdict in sorted(six.iteritems(live_refs),
                             key=lambda x: x[0].__name__):
        if not wdict:
            continue
        if issubclass(cls, ignore):
            continue
        oldest = min(six.itervalues(wdict))
        s += "%-30s %6d   oldest: %ds ago\n" % (
            cls.__name__, len(wdict), now - oldest
        )
    return s


def print_live_refs(*a, **kw):
    """Print a report of live references, grouped by class name.

    :param ignore: if given, all objects from the specified class (or tuple of
        classes) will be ignored.
    """
    print(format_live_refs(*a, **kw))


def get_oldest(class_name):
    """Return the oldest object alive with the given class name, or ``None`` if
    none is found. Use :func:`print_live_refs` first to get a list of all
    tracked live objects per class name."""
    for cls, wdict in six.iteritems(live_refs):
        if cls.__name__ == class_name:
            if not wdict:
                break
            return min(six.iteritems(wdict), key=itemgetter(1))[0]


def iter_all(class_name):
    """Return an iterator over all objects alive with the given class name, or
    ``None`` if none is found. Use :func:`print_live_refs` first to get a list
    of all tracked live objects per class name."""
    for cls, wdict in six.iteritems(live_refs):
        if cls.__name__ == class_name:
            return six.iterkeys(wdict)
