"""
This module contains data types used by Scrapy which are not included in the
Python Standard Library.

This module must not depend on any module outside the Standard Library.
"""

from __future__ import annotations

import collections
import warnings
import weakref
from collections import OrderedDict
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, AnyStr, TypeVar

from scrapy.exceptions import ScrapyDeprecationWarning

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    # typing.Self requires Python 3.11
    from typing_extensions import Self


_KT = TypeVar("_KT")
_VT = TypeVar("_VT")


class CaselessDict(dict):
    __slots__ = ()

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        from scrapy.http.headers import Headers

        if issubclass(cls, CaselessDict) and not issubclass(cls, Headers):
            warnings.warn(
                "scrapy.utils.datatypes.CaselessDict is deprecated,"
                " please use scrapy.utils.datatypes.CaseInsensitiveDict instead",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        return super().__new__(cls, *args, **kwargs)

    def __init__(
        self,
        seq: Mapping[AnyStr, Any] | Iterable[tuple[AnyStr, Any]] | None = None,
    ):
        super().__init__()
        if seq:
            self.update(seq)

    def __getitem__(self, key: AnyStr) -> Any:
        return dict.__getitem__(self, self.normkey(key))

    def __setitem__(self, key: AnyStr, value: Any) -> None:
        dict.__setitem__(self, self.normkey(key), self.normvalue(value))

    def __delitem__(self, key: AnyStr) -> None:
        dict.__delitem__(self, self.normkey(key))

    def __contains__(self, key: AnyStr) -> bool:  # type: ignore[override]
        return dict.__contains__(self, self.normkey(key))

    has_key = __contains__

    def __copy__(self) -> Self:
        return self.__class__(self)

    copy = __copy__

    def normkey(self, key: AnyStr) -> AnyStr:
        """Method to normalize dictionary key access"""
        return key.lower()

    def normvalue(self, value: Any) -> Any:
        """Method to normalize values prior to be set"""
        return value

    def get(self, key: AnyStr, def_val: Any = None) -> Any:
        return dict.get(self, self.normkey(key), self.normvalue(def_val))

    def setdefault(self, key: AnyStr, def_val: Any = None) -> Any:
        return dict.setdefault(self, self.normkey(key), self.normvalue(def_val))  # type: ignore[arg-type]

    # doesn't fully implement MutableMapping.update()
    def update(self, seq: Mapping[AnyStr, Any] | Iterable[tuple[AnyStr, Any]]) -> None:  # type: ignore[override]
        seq = seq.items() if isinstance(seq, Mapping) else seq
        iseq = ((self.normkey(k), self.normvalue(v)) for k, v in seq)
        super().update(iseq)

    @classmethod
    def fromkeys(cls, keys: Iterable[AnyStr], value: Any = None) -> Self:  # type: ignore[override]
        return cls((k, value) for k in keys)  # type: ignore[misc]

    def pop(self, key: AnyStr, *args: Any) -> Any:
        return dict.pop(self, self.normkey(key), *args)


class CaseInsensitiveDict(collections.UserDict):
    """A dict-like structure that accepts strings or bytes
    as keys and allows case-insensitive lookups.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

    def __init__(self, limit: int | None = None):
        super().__init__()
        self.limit: int | None = limit

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

    def __init__(self, limit: int | None = None):
        super().__init__()
        self.data: LocalCache = LocalCache(limit=limit)

    def __setitem__(self, key: _KT, value: _VT) -> None:
        try:
            super().__setitem__(key, value)
        except TypeError:
            pass  # key is not weak-referenceable, skip caching

    def __getitem__(self, key: _KT) -> _VT | None:  # type: ignore[override]
        try:
            return super().__getitem__(key)
        except (TypeError, KeyError):
            return None  # key is either not weak-referenceable or not cached


class SequenceExclude:
    """Object to test if an item is NOT within some sequence."""

    def __init__(self, seq: Sequence[Any]):
        self.seq: Sequence[Any] = seq

    def __contains__(self, item: Any) -> bool:
        return item not in self.seq
