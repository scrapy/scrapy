from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from w3lib.http import headers_dict_to_raw

from scrapy.utils.datatypes import CaseInsensitiveDict
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from collections.abc import Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self


_RawValue: TypeAlias = bytes | str | int


class Headers(dict):  # type: ignore[type-arg]
    """Case insensitive http headers dictionary"""

    def __init__(
        self,
        seq: Mapping[str, Any]
        | Mapping[bytes, Any]
        | Iterable[tuple[str | bytes, Any]]
        | None = None,
        encoding: str = "utf-8",
    ):
        self.encoding: str = encoding
        super().__init__()
        if seq:
            self.update(seq)

    def __setitem__(self, key: str | bytes, value: Any) -> None:
        dict.__setitem__(self, self.normkey(key), self.normvalue(value))

    def __delitem__(self, key: str | bytes) -> None:
        dict.__delitem__(self, self.normkey(key))

    def __contains__(self, key: str | bytes) -> bool:  # type: ignore[override]
        return dict.__contains__(self, self.normkey(key))

    has_key = __contains__

    def setdefault(self, key: str | bytes, def_val: Any = None) -> Any:
        return dict.setdefault(self, self.normkey(key), self.normvalue(def_val))

    @classmethod
    def fromkeys(  # type: ignore[override]
        cls, keys: Iterable[str | bytes], value: Any = None
    ) -> Self:
        return cls((k, value) for k in keys)

    def pop(self, key: str | bytes, *args: Any) -> Any:
        return dict.pop(self, self.normkey(key), *args)

    def update(  # type: ignore[override]
        self,
        seq: Mapping[str, Any]
        | Mapping[bytes, Any]
        | Iterable[tuple[str | bytes, Any]],
    ) -> None:
        seq = seq.items() if isinstance(seq, Mapping) else seq
        iseq: dict[bytes, list[bytes]] = {}
        for k, v in seq:
            iseq.setdefault(self.normkey(k), []).extend(self.normvalue(v))
        dict.update(self, iseq)

    def normkey(self, key: str | bytes) -> bytes:
        """Normalize key to bytes"""
        return self._tobytes(key.title())

    def normvalue(self, value: _RawValue | Iterable[_RawValue]) -> list[bytes]:
        """Normalize values to bytes"""
        _value: Iterable[_RawValue]
        if value is None:
            _value = []
        elif isinstance(value, (str, bytes)):
            _value = [value]
        elif hasattr(value, "__iter__"):
            _value = value
        else:
            _value = [value]

        return [self._tobytes(x) for x in _value]

    def _tobytes(self, x: _RawValue) -> bytes:
        if isinstance(x, bytes):
            return x
        if isinstance(x, str):
            return x.encode(self.encoding)
        if isinstance(x, int):
            return str(x).encode(self.encoding)
        raise TypeError(f"Unsupported value type: {type(x)}")

    def __getitem__(self, key: str | bytes) -> bytes | None:
        try:
            return cast("list[bytes]", dict.__getitem__(self, self.normkey(key)))[-1]
        except IndexError:
            return None

    def get(self, key: str | bytes, def_val: Any = None) -> bytes | None:
        try:
            return cast(
                "list[bytes]",
                dict.get(self, self.normkey(key), self.normvalue(def_val)),
            )[-1]
        except IndexError:
            return None

    def getlist(self, key: str | bytes, def_val: Any = None) -> list[bytes]:
        try:
            return cast("list[bytes]", dict.__getitem__(self, self.normkey(key)))
        except KeyError:
            if def_val is not None:
                return self.normvalue(def_val)
            return []

    def setlist(self, key: str | bytes, list_: Iterable[_RawValue]) -> None:
        self[key] = list_

    def setlistdefault(
        self, key: str | bytes, default_list: Iterable[_RawValue] = ()
    ) -> Any:
        return self.setdefault(key, default_list)

    def appendlist(self, key: str | bytes, value: Iterable[_RawValue]) -> None:
        lst = self.getlist(key)
        lst.extend(self.normvalue(value))
        self[key] = lst

    def items(self) -> Iterable[tuple[bytes, list[bytes]]]:  # type: ignore[override]
        return ((k, self.getlist(k)) for k in self.keys())

    def values(self) -> list[bytes | None]:  # type: ignore[override]
        return [
            self[k]
            for k in self.keys()  # pylint: disable=consider-using-dict-items
        ]

    def to_string(self) -> bytes:
        return headers_dict_to_raw(self)

    def to_unicode_dict(self) -> CaseInsensitiveDict:
        """Return headers as a CaseInsensitiveDict with str keys
        and str values. Multiple values are joined with ','.
        """
        return CaseInsensitiveDict(
            (
                to_unicode(key, encoding=self.encoding),
                to_unicode(b",".join(value), encoding=self.encoding),
            )
            for key, value in self.items()
        )

    def to_tuple_list(self) -> list[tuple[str, str]]:
        """Return headers as a list of ``(key, value)`` tuples.

        Multiple values are represented as multiple tuples with the same key.
        """
        return [
            (key.decode(self.encoding), value.decode(self.encoding))
            for key, values in self.items()
            for value in values
        ]

    def __copy__(self) -> Self:
        return self.__class__(self)

    copy = __copy__
