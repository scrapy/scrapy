"""This module provides some functions and classes to record and report
references to live object instances.

If you want live objects for a particular class to be tracked, you only have to
subclass from object_ref (instead of object).

About performance: This library has a minimal performance impact when enabled,
and no performance penalty at all when disabled (as object_ref becomes just an
alias to object in that case).
"""

import weakref
from time import time
from operator import itemgetter
from collections import defaultdict


NoneType = type(None)
live_refs = defaultdict(weakref.WeakKeyDictionary)


class object_ref:
    """Inherit from this class to a keep a record of live instances"""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        live_refs[cls][obj] = time()
        return obj


def format_live_refs(ignore=NoneType):
    """Return a tabular representation of tracked objects"""
    s = "Live References\n\n"
    now = time()
    for cls, wdict in sorted(live_refs.items(),
                             key=lambda x: x[0].__name__):
        if not wdict:
            continue
        if issubclass(cls, ignore):
            continue
        oldest = min(wdict.values())
        s += "%-30s %6d   oldest: %ds ago\n" % (
            cls.__name__, len(wdict), now - oldest
        )
    return s


def print_live_refs(*a, **kw):
    """Print tracked objects"""
    print(format_live_refs(*a, **kw))


def get_oldest(class_name):
    """Get the oldest object for a specific class name"""
    for cls, wdict in live_refs.items():
        if cls.__name__ == class_name:
            if not wdict:
                break
            return min(wdict.items(), key=itemgetter(1))[0]


def iter_all(class_name):
    """Iterate over all objects of the same class by its class name"""
    for cls, wdict in live_refs.items():
        if cls.__name__ == class_name:
            return wdict.keys()
