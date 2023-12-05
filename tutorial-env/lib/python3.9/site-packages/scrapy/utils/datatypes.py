"""
This module contains data types used by Scrapy which are not included in the
Python Standard Library.

This module must not depend on any module outside the Standard Library.
"""

import collections
import warnings
import weakref
from collections.abc import Mapping
from typing import Any, AnyStr, Optional, OrderedDict, Sequence, TypeVar

from scrapy.exceptions import ScrapyDeprecationWarning

_KT = TypeVar("_KT")
_VT = TypeVar("_VT")


class CaselessDict(dict):
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        from scrapy.http.headers import Headers

        if issubclass(cls, CaselessDict) and not issubclass(cls, Headers):
            warnings.warn(
                "scrapy.utils.datatypes.CaselessDict is deprecated,"
                " please use scrapy.utils.datatypes.CaseInsensitiveDict instead",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        return super().__new__(cls, *args, **kwargs)

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
        """Method to normalize values prior to be set"""
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


class CaseInsensitiveDict(collections.UserDict):
    """A dict-like structure that accepts strings or bytes
    as keys and allows case-insensitive lookups.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._keys: dict = {}
        super().__init__(*args, **kwargs)

    def __getitem__(self, key: AnyStr) -> Any:
        normalized_key = self._normkey(key)
        return super().__getitem__(self._keys[normalized_key.lower()])

    def __setitem__(self, key: AnyStr, value: Any) -> None:
        normalized_key = self._normkey(key)
        try:
            lower_key = self._keys[normalized_key.lower()]
            del self[lower_key]
        except KeyError:
            pass
        super().__setitem__(normalized_key, self._normvalue(value))
        self._keys[normalized_key.lower()] = normalized_key

    def __delitem__(self, key: AnyStr) -> None:
        normalized_key = self._normkey(key)
        stored_key = self._keys.pop(normalized_key.lower())
        super().__delitem__(stored_key)

    def __contains__(self, key: AnyStr) -> bool:  # type: ignore[override]
        normalized_key = self._normkey(key)
        return normalized_key.lower() in self._keys

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {super().__repr__()}>"

    def _normkey(self, key: AnyStr) -> AnyStr:
        return key

    def _normvalue(self, value: Any) -> Any:
        return value


class LocalCache(OrderedDict[_KT, _VT]):
    """Dictionary with a finite number of keys.

    Older items expires first.
    """

    def __init__(self, limit: Optional[int] = None):
        super().__init__()
        self.limit: Optional[int] = limit

    def __setitem__(self, key: _KT, value: _VT) -> None:
        if self.limit:
            while len(self) >= self.limit:
                self.popitem(last=False)
        super().__setitem__(key, value)


class LocalWeakReferencedCache(weakref.WeakKeyDictionary):
    """
    A weakref.WeakKeyDictionary implementation that uses LocalCache as its
    underlying data structure, making it ordered and capable of being size-limited.

    Useful for memoization, while avoiding keeping received
    arguments in memory only because of the cached references.

    Note: like LocalCache and unlike weakref.WeakKeyDictionary,
    it cannot be instantiated with an initial dictionary.
    """

    def __init__(self, limit: Optional[int] = None):
        super().__init__()
        self.data: LocalCache = LocalCache(limit=limit)

    def __setitem__(self, key: _KT, value: _VT) -> None:
        try:
            super().__setitem__(key, value)
        except TypeError:
            pass  # key is not weak-referenceable, skip caching

    def __getitem__(self, key: _KT) -> Optional[_VT]:  # type: ignore[override]
        try:
            return super().__getitem__(key)
        except (TypeError, KeyError):
            return None  # key is either not weak-referenceable or not cached


class SequenceExclude:
    """Object to test if an item is NOT within some sequence."""

    def __init__(self, seq: Sequence):
        self.seq: Sequence = seq

    def __contains__(self, item: Any) -> bool:
        return item not in self.seq
