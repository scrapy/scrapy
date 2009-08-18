"""This module provides some functions and classes to record and report live
references to object instances, for certain classes"""

import weakref
from collections import defaultdict
from time import time
from operator import itemgetter

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

def print_live_refs():
    print "Live References"
    print
    now = time()
    for cls, wdict in live_refs.iteritems():
        if not wdict:
            continue
        oldest = min(wdict.itervalues())
        print "%-30s %6d   oldest: %ds ago" % (cls.__name__, len(wdict), \
            now-oldest)

def get_oldest(class_name):
    for cls, wdict in live_refs.iteritems():
        if cls.__name__ == class_name:
            if wdict:
                return min(wdict.iteritems(), key=itemgetter(1))[0]
