from __future__ import absolute_import, division, print_function

import sys


PY2 = sys.version_info[0] == 2


if PY2:
    import types

    # We 'bundle' isclass instead of using inspect as importing inspect is
    # fairly expensive (order of 10-15 ms for a modern machine in 2016)
    def isclass(klass):
        return isinstance(klass, (type, types.ClassType))

    # TYPE is used in exceptions, repr(int) is different on Python 2 and 3.
    TYPE = "type"

    def iteritems(d):
        return d.iteritems()

    def iterkeys(d):
        return d.iterkeys()
else:
    def isclass(klass):
        return isinstance(klass, type)

    TYPE = "class"

    def iteritems(d):
        return d.items()

    def iterkeys(d):
        return d.keys()
