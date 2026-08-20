"""
This module contains data types used by Scrapy which are not included in the
Python Standard Library.
"""

from __future__ import annotations

import collections
import contextlib
import weakref
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Container

    # typing.Self requires Python 3.11
    from typing_extensions import Self


_KT = TypeVar("_KT")
_VT = TypeVar("_VT")


class CaseInsensitiveDict(collections.UserDict[str | bytes, Any]):
    """A dict-like structure that accepts strings or bytes
    as keys and allows case-insensitive lookups.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._keys: dict[str | bytes, Any] = {}
        super().__init__(*args, **kwargs)

    def __getitem__(self, key: str | bytes) -> Any:
        normalized_key = self._normkey(key)
        return super().__getitem__(self._keys[normalized_key.lower()])

    def __setitem__(self, key: str | bytes, value: Any) -> None:
        normalized_key = self._normkey(key)
        try:
            lower_key = self._keys[normalized_key.lower()]
            del self[lower_key]
        except KeyError:
            pass
        super().__setitem__(normalized_key, self._normvalue(value))
        self._keys[normalized_key.lower()] = normalized_key

    def __delitem__(self, key: str | bytes) -> None:
        normalized_key = self._normkey(key)
        stored_key = self._keys.pop(normalized_key.lower())
        super().__delitem__(stored_key)

    def __contains__(self, key: str | bytes) -> bool:  # type: ignore[override]
        normalized_key = self._normkey(key)
        return normalized_key.lower() in self._keys

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {super().__repr__()}>"

    # UserDict.copy() shallow-copies the instance, which would share self._keys
    # between the copy and the original.
    def __copy__(self) -> Self:
        new = self.__class__()
        new.data = self.data.copy()
        new._keys = self._keys.copy()
        return new

    copy = __copy__

    # UserDict.__ior__ updates self.data directly, which would leave self._keys
    # out of date.
    def __ior__(self, other: Any) -> Self:  # type: ignore[override,misc]
        self.update(other)
        return self

    def _normkey(self, key: str | bytes) -> str | bytes:
        return key

    def _normvalue(self, value: Any) -> Any:
        return value


class LocalCache(OrderedDict[_KT, _VT]):
    """Dictionary with a finite number of keys.

    Older items expires first.
    """

    def __init__(self, limit: int | None = None):
        super().__init__()
        self.limit: int | None = limit

    def __setitem__(self, key: _KT, value: _VT) -> None:
        if self.limit is not None:
            if self.limit == 0:
                return
            while len(self) >= self.limit:
                self.popitem(last=False)
        super().__setitem__(key, value)


class LocalWeakReferencedCache(weakref.WeakKeyDictionary[_KT, _VT | None]):
    """
    A weakref.WeakKeyDictionary implementation that uses LocalCache as its
    underlying data structure, making it ordered and capable of being size-limited.

    Useful for memoization, while avoiding keeping received
    arguments in memory only because of the cached references.

    Note: like LocalCache and unlike weakref.WeakKeyDictionary,
    it cannot be instantiated with an initial dictionary.
    """

    def __init__(self, limit: int | None = None):
        super().__init__()
        self.data: LocalCache[_KT, _VT] = LocalCache(limit=limit)

    def __setitem__(self, key: _KT, value: _VT | None) -> None:
        # if raised, key is not weak-referenceable, skip caching
        with contextlib.suppress(TypeError):
            super().__setitem__(key, value)

    def __getitem__(self, key: _KT) -> _VT | None:
        try:
            return cast("_VT", super().__getitem__(key))
        except (TypeError, KeyError):
            return None  # key is either not weak-referenceable or not cached


class SequenceExclude:
    """Object to test if an item is NOT within some sequence."""

    def __init__(self, seq: Container[Any]):
        self.seq: Container[Any] = seq

    def __contains__(self, item: Any) -> bool:
        return item not in self.seq
