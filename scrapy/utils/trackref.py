"""This module provides some functions and classes to record and report
references to live object instances.

If you want live objects for a particular class to be tracked, you only have to
subclass form object_ref (instead of object). Also, remember to turn on
tracking by enabling the TRACK_REFS setting.

About performance: This library has a minimal performance impact when enabled,
and no performance penalty at all when disabled (as object_ref becomes just an
alias to object in that case).
"""

import weakref, os
from collections import defaultdict
from time import time
from operator import itemgetter
from types import NoneType

from scrapy.conf import settings

live_refs = defaultdict(weakref.WeakKeyDictionary)

class object_ref(object):
    """Inherit from this class (instead of object) to a keep a record of live
    instances"""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        live_refs[cls][obj] = time()
        return obj

if not settings.getbool('TRACK_REFS'):
    object_ref = object

def format_live_refs(ignore=NoneType):
    if object_ref is object:
        return "The trackref module is disabled. Use TRACK_REFS setting to enable it."
    s = "Live References" + os.linesep + os.linesep
    now = time()
    for cls, wdict in live_refs.iteritems():
        if not wdict:
            continue
        if issubclass(cls, ignore):
            continue
        oldest = min(wdict.itervalues())
        s += "%-30s %6d   oldest: %ds ago" % (cls.__name__, len(wdict), \
            now-oldest) + os.linesep
    return s

def print_live_refs(*a, **kw):
    print format_live_refs(*a, **kw)

def get_oldest(class_name):
    for cls, wdict in live_refs.iteritems():
        if cls.__name__ == class_name:
            if wdict:
                return min(wdict.iteritems(), key=itemgetter(1))[0]

def iter_all(class_name):
    for cls, wdict in live_refs.iteritems():
        if cls.__name__ == class_name:
            return wdict.iterkeys()
