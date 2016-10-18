##############################################################################
#
# Copyright (c) 2003 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Compute a resolution order for an object and its bases
"""
__docformat__ = 'restructuredtext'

def _mergeOrderings(orderings):
    """Merge multiple orderings so that within-ordering order is preserved

    Orderings are constrained in such a way that if an object appears
    in two or more orderings, then the suffix that begins with the
    object must be in both orderings.

    For example:

    >>> _mergeOrderings([
    ... ['x', 'y', 'z'],
    ... ['q', 'z'],
    ... [1, 3, 5],
    ... ['z']
    ... ])
    ['x', 'y', 'q', 1, 3, 5, 'z']

    """

    seen = {}
    result = []
    for ordering in reversed(orderings):
        for o in reversed(ordering):
            if o not in seen:
                seen[o] = 1
                result.insert(0, o)

    return result

def _flatten(ob):
    result = [ob]
    i = 0
    for ob in iter(result):
        i += 1
        # The recursive calls can be avoided by inserting the base classes
        # into the dynamically growing list directly after the currently
        # considered object;  the iterator makes sure this will keep working
        # in the future, since it cannot rely on the length of the list
        # by definition.
        result[i:i] = ob.__bases__
    return result


def ro(object):
    """Compute a "resolution order" for an object
    """
    return _mergeOrderings([_flatten(object)])
