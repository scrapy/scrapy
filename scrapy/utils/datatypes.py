"""
This module contains data types used by Scrapy which are not included in the
Python Standard Library.

This module must not depend on any module outside the Standard Library.
"""

import collections
import weakref
from collections.abc import Mapping
from datetime import datetime


class CaselessDict(dict):

    __slots__ = ()

    def __init__(self, seq=None):
        super().__init__()
        if seq:
            self.update(seq)

    def __getitem__(self, key):
        return dict.__getitem__(self, self.normkey(key))

    def __setitem__(self, key, value):
        dict.__setitem__(self, self.normkey(key), self.normvalue(value))

    def __delitem__(self, key):
        dict.__delitem__(self, self.normkey(key))

    def __contains__(self, key):
        return dict.__contains__(self, self.normkey(key))
    has_key = __contains__

    def __copy__(self):
        return self.__class__(self)
    copy = __copy__

    def normkey(self, key):
        """Method to normalize dictionary key access"""
        return key.lower()

    def normvalue(self, value):
        """Method to normalize values prior to be setted"""
        return value

    def get(self, key, def_val=None):
        return dict.get(self, self.normkey(key), self.normvalue(def_val))

    def setdefault(self, key, def_val=None):
        return dict.setdefault(self, self.normkey(key), self.normvalue(def_val))

    def update(self, seq):
        seq = seq.items() if isinstance(seq, Mapping) else seq
        iseq = ((self.normkey(k), self.normvalue(v)) for k, v in seq)
        super().update(iseq)

    @classmethod
    def fromkeys(cls, keys, value=None):
        return cls((k, value) for k in keys)

    def pop(self, key, *args):
        return dict.pop(self, self.normkey(key), *args)


class LocalCache(collections.OrderedDict):
    """
    Dictionary with a finite number of keys.
    Older items expire first.
    """

    def __init__(self, limit=None, time_limit=None):
        super().__init__()
        self.limit = limit
        self.time_limit = time_limit

    def __setitem__(self, key, value):
        now = datetime.now()
        value = (value, now)

        if self.limit is not None:
            while len(self) >= self.limit:
                self.popitem(last=False)

        while True:
            try:
                val = self.values().__iter__().__next__()
            except StopIteration as e:
                break
            
            if (datetime.now() - val[1]).total_seconds() > self.time_limit:
                self.popitem(last=False)
            else:
                break
            
        super().__setitem__(key, value)

    def __getitem__(self, key):
        if self.time_limit is None:
            return super().__getitem__(key)[0]

        while True:
            try:
                val = self.values().__iter__().__next__()
            except StopIteration as e:
                break
            
            if (datetime.now() - val[1]).total_seconds() > self.time_limit:
                self.popitem(last=False)
            else:
                break
        
        val = (super().__getitem__(key)[0],datetime.now())
        super().__setitem__(key, val)
        return val[0]



class LocalWeakReferencedCache(weakref.WeakKeyDictionary):
    """
    A weakref.WeakKeyDictionary implementation that uses LocalCache as its
    underlying data structure, making it ordered and capable of being size-limited.

    Useful for memoization, while avoiding keeping received
    arguments in memory only because of the cached references.

    Note: like LocalCache and unlike weakref.WeakKeyDictionary,
    it cannot be instantiated with an initial dictionary.
    """

    def __init__(self, limit=None):
        super().__init__()
        self.data = LocalCache(limit=limit)

    def __setitem__(self, key, value):
        try:
            super().__setitem__(key, value)
        except TypeError:
            pass  # key is not weak-referenceable, skip caching

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except (TypeError, KeyError):
            return None  # key is either not weak-referenceable or not cached


class SequenceExclude:
    """Object to test if an item is NOT within some sequence."""

    def __init__(self, seq):
        self.seq = seq

    def __contains__(self, item):
        return item not in self.seq
