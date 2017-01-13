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
"""Mapping Interfaces
"""
from zope.interface import Interface

class IItemMapping(Interface):
    """Simplest readable mapping object
    """

    def __getitem__(key):
        """Get a value for a key

        A KeyError is raised if there is no value for the key.
        """


class IReadMapping(IItemMapping):
    """Basic mapping interface
    """

    def get(key, default=None):
        """Get a value for a key

        The default is returned if there is no value for the key.
        """

    def __contains__(key):
        """Tell if a key exists in the mapping."""


class IWriteMapping(Interface):
    """Mapping methods for changing data"""
    
    def __delitem__(key):
        """Delete a value from the mapping using the key."""

    def __setitem__(key, value):
        """Set a new item in the mapping."""
        

class IEnumerableMapping(IReadMapping):
    """Mapping objects whose items can be enumerated.
    """

    def keys():
        """Return the keys of the mapping object.
        """

    def __iter__():
        """Return an iterator for the keys of the mapping object.
        """

    def values():
        """Return the values of the mapping object.
        """

    def items():
        """Return the items of the mapping object.
        """

    def __len__():
        """Return the number of items.
        """

class IMapping(IWriteMapping, IEnumerableMapping):
    ''' Simple mapping interface '''

class IIterableMapping(IEnumerableMapping):

    def iterkeys():
        "iterate over keys; equivalent to __iter__"

    def itervalues():
        "iterate over values"

    def iteritems():
        "iterate over items"

class IClonableMapping(Interface):
    
    def copy():
        "return copy of dict"

class IExtendedReadMapping(IIterableMapping):
    
    def has_key(key):
        """Tell if a key exists in the mapping; equivalent to __contains__"""

class IExtendedWriteMapping(IWriteMapping):
    
    def clear():
        "delete all items"
    
    def update(d):
        " Update D from E: for k in E.keys(): D[k] = E[k]"
    
    def setdefault(key, default=None):
        "D.setdefault(k[,d]) -> D.get(k,d), also set D[k]=d if k not in D"
    
    def pop(k, *args):
        """remove specified key and return the corresponding value
        *args may contain a single default value, or may not be supplied.
        If key is not found, default is returned if given, otherwise 
        KeyError is raised"""
    
    def popitem():
        """remove and return some (key, value) pair as a
        2-tuple; but raise KeyError if mapping is empty"""

class IFullMapping(
    IExtendedReadMapping, IExtendedWriteMapping, IClonableMapping, IMapping):
    ''' Full mapping interface ''' # IMapping included so tests for IMapping
    # succeed with IFullMapping
