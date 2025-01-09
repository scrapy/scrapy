from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, AnyStr, Union, cast

from w3lib.http import headers_dict_to_raw

from scrapy.utils.datatypes import CaseInsensitiveDict, CaselessDict
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from collections.abc import Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self


_RawValueT = Union[bytes, str, int]


# isn't fully compatible typing-wise with either dict or CaselessDict,
# but it needs refactoring anyway, see also https://github.com/scrapy/scrapy/pull/5146
class Headers(CaselessDict):
    """Case insensitive http headers dictionary"""

    def __init__(
        self,
        seq: Mapping[AnyStr, Any] | Iterable[tuple[AnyStr, Any]] | None = None,
        encoding: str = "utf-8",
    ):
        self.encoding: str = encoding
        super().__init__(seq)

    def update(  # type: ignore[override]
        self, seq: Mapping[AnyStr, Any] | Iterable[tuple[AnyStr, Any]]
    ) -> None:
        seq = seq.items() if isinstance(seq, Mapping) else seq
        iseq: dict[bytes, list[bytes]] = {}
        for k, v in seq:
            iseq.setdefault(self.normkey(k), []).extend(self.normvalue(v))
        super().update(iseq)

    def normkey(self, key: AnyStr) -> bytes:  # type: ignore[override]
        """Normalize key to bytes"""
        return self._tobytes(key.title())

    def normvalue(self, value: _RawValueT | Iterable[_RawValueT]) -> list[bytes]:
        """Normalize values to bytes"""
        _value: Iterable[_RawValueT]
        if value is None:
            _value = []
        elif isinstance(value, (str, bytes)):
            _value = [value]
        elif hasattr(value, "__iter__"):
            _value = value
        else:
            _value = [value]

        return [self._tobytes(x) for x in _value]

    def _tobytes(self, x: _RawValueT) -> bytes:
        if isinstance(x, bytes):
            return x
        if isinstance(x, str):
            return x.encode(self.encoding)
        if isinstance(x, int):
            return str(x).encode(self.encoding)
        raise TypeError(f"Unsupported value type: {type(x)}")

    def __getitem__(self, key: AnyStr) -> bytes | None:
        try:
            return cast(list[bytes], super().__getitem__(key))[-1]
        except IndexError:
            return None

    def get(self, key: AnyStr, def_val: Any = None) -> bytes | None:
        try:
            return cast(list[bytes], super().get(key, def_val))[-1]
        except IndexError:
            return None

    def getlist(self, key: AnyStr, def_val: Any = None) -> list[bytes]:
        try:
            return cast(list[bytes], super().__getitem__(key))
        except KeyError:
            if def_val is not None:
                return self.normvalue(def_val)
            return []

    def setlist(self, key: AnyStr, list_: Iterable[_RawValueT]) -> None:
        self[key] = list_

    def setlistdefault(
        self, key: AnyStr, default_list: Iterable[_RawValueT] = ()
    ) -> Any:
        return self.setdefault(key, default_list)

    def appendlist(self, key: AnyStr, value: Iterable[_RawValueT]) -> None:
        lst = self.getlist(key)
        lst.extend(self.normvalue(value))
        self[key] = lst

    def items(self) -> Iterable[tuple[bytes, list[bytes]]]:  # type: ignore[override]
        return ((k, self.getlist(k)) for k in self.keys())

    def values(self) -> list[bytes | None]:  # type: ignore[override]
        return [
            self[k] for k in self.keys()  # pylint: disable=consider-using-dict-items
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

    def __copy__(self) -> Self:
        return self.__class__(self)

    copy = __copy__
