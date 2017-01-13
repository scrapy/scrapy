##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
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
"""Sequence Interfaces
"""
__docformat__ = 'restructuredtext'
from zope.interface import Interface

class IMinimalSequence(Interface):
    """Most basic sequence interface.

    All sequences are iterable.  This requires at least one of the
    following:

    - a `__getitem__()` method that takes a single argument; interger
      values starting at 0 must be supported, and `IndexError` should
      be raised for the first index for which there is no value, or

    - an `__iter__()` method that returns an iterator as defined in
      the Python documentation (http://docs.python.org/lib/typeiter.html).

    """

    def __getitem__(index):
        """`x.__getitem__(index)` <==> `x[index]`

        Declaring this interface does not specify whether `__getitem__`
        supports slice objects."""

class IFiniteSequence(IMinimalSequence):

    def __len__():
        """`x.__len__()` <==> `len(x)`"""

class IReadSequence(IFiniteSequence):
    """read interface shared by tuple and list"""

    def __contains__(item):
        """`x.__contains__(item)` <==> `item in x`"""

    def __lt__(other):
        """`x.__lt__(other)` <==> `x < other`"""

    def __le__(other):
        """`x.__le__(other)` <==> `x <= other`"""

    def __eq__(other):
        """`x.__eq__(other)` <==> `x == other`"""

    def __ne__(other):
        """`x.__ne__(other)` <==> `x != other`"""

    def __gt__(other):
        """`x.__gt__(other)` <==> `x > other`"""

    def __ge__(other):
        """`x.__ge__(other)` <==> `x >= other`"""

    def __add__(other):
        """`x.__add__(other)` <==> `x + other`"""

    def __mul__(n):
        """`x.__mul__(n)` <==> `x * n`"""

    def __rmul__(n):
        """`x.__rmul__(n)` <==> `n * x`"""

    def __getslice__(i, j):
        """`x.__getslice__(i, j)` <==> `x[i:j]`

        Use of negative indices is not supported.

        Deprecated since Python 2.0 but still a part of `UserList`.
        """

class IExtendedReadSequence(IReadSequence):
    """Full read interface for lists"""

    def count(item):
        """Return number of occurrences of value"""

    def index(item, *args):
        """Return first index of value

        `L.index(value, [start, [stop]])` -> integer"""

class IUniqueMemberWriteSequence(Interface):
    """The write contract for a sequence that may enforce unique members"""

    def __setitem__(index, item):
        """`x.__setitem__(index, item)` <==> `x[index] = item`

        Declaring this interface does not specify whether `__setitem__`
        supports slice objects.
        """

    def __delitem__(index):
        """`x.__delitem__(index)` <==> `del x[index]`

        Declaring this interface does not specify whether `__delitem__`
        supports slice objects.
        """

    def __setslice__(i, j, other):
        """`x.__setslice__(i, j, other)` <==> `x[i:j]=other`

        Use of negative indices is not supported.

        Deprecated since Python 2.0 but still a part of `UserList`.
        """

    def __delslice__(i, j):
        """`x.__delslice__(i, j)` <==> `del x[i:j]`

        Use of negative indices is not supported.

        Deprecated since Python 2.0 but still a part of `UserList`.
        """
    def __iadd__(y):
        """`x.__iadd__(y)` <==> `x += y`"""

    def append(item):
        """Append item to end"""

    def insert(index, item):
        """Insert item before index"""

    def pop(index=-1):
        """Remove and return item at index (default last)"""

    def remove(item):
        """Remove first occurrence of value"""

    def reverse():
        """Reverse *IN PLACE*"""

    def sort(cmpfunc=None):
        """Stable sort *IN PLACE*; `cmpfunc(x, y)` -> -1, 0, 1"""

    def extend(iterable):
        """Extend list by appending elements from the iterable"""

class IWriteSequence(IUniqueMemberWriteSequence):
    """Full write contract for sequences"""

    def __imul__(n):
        """`x.__imul__(n)` <==> `x *= n`"""

class ISequence(IReadSequence, IWriteSequence):
    """Full sequence contract"""
