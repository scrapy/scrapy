from __future__ import annotations

import warnings
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeAlias, cast

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._datatypes import CaseInsensitiveDict

if TYPE_CHECKING:
    from collections.abc import Iterable


_RawValue: TypeAlias = bytes | str | int


class Headers(dict):  # type: ignore[type-arg]
    """Headers of a :class:`~scrapy.Request` or a
    :class:`~scrapy.http.Response`.

    *seq* is a mapping of header names to values, or an iterable of
    ``(name, value)`` pairs. Names and values can be :class:`bytes` or
    :class:`str`, and values can also be :class:`int`. A value can be a list,
    for a header with several values, or ``None``, for a header that must not
    be sent. :class:`str` names and values are encoded with *encoding*.

    Names and values are stored as :class:`bytes`. Lookups are
    case-insensitive; the first spelling of a name is stored.

    If several values of a header are stored, ``headers[name]`` and :meth:`get`
    return the last one, :meth:`getlist` returns all of them, and
    ``del headers[name]`` removes all of them. :attr:`raw` and
    :meth:`to_tuple_list` return all values of all headers.

    A header set to ``None`` stays in the headers without a value:
    ``name in headers`` is ``True`` and ``headers[name]`` is ``None``. It is
    not sent, and components that add default headers, such as
    :class:`~scrapy.downloadermiddlewares.useragent.UserAgentMiddleware` and
    :class:`~scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware`,
    do not add it.
    """

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
        dict.__setitem__(self, self._normkey(key), self._normvalue(value))

    def __delitem__(self, key: str | bytes) -> None:
        dict.__delitem__(self, self._normkey(key))

    def __contains__(self, key: str | bytes) -> bool:  # type: ignore[override]
        return dict.__contains__(self, self._normkey(key))

    def has_key(self, key: str | bytes) -> bool:
        warnings.warn(
            'Headers.has_key() is deprecated, use the "in" operator instead.',
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return key in self

    def setdefault(self, key: str | bytes, def_val: Any = None) -> Any:
        """Set the *key* header to *def_val* if the header is missing.

        A header set to ``None`` is not considered missing.
        """
        return dict.setdefault(self, self._normkey(key), self._normvalue(def_val))

    @classmethod
    def fromkeys(  # type: ignore[override]
        cls, keys: Iterable[str | bytes], value: Any = None
    ) -> Self:
        warnings.warn(
            "Headers.fromkeys() is deprecated, pass (key, value) pairs to"
            " Headers() instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return cls((k, value) for k in keys)

    def pop(self, key: str | bytes, *args: Any) -> Any:
        return dict.pop(self, self._normkey(key), *args)

    def update(  # type: ignore[override]
        self,
        seq: Mapping[str, Any]
        | Mapping[bytes, Any]
        | Iterable[tuple[str | bytes, Any]],
    ) -> None:
        items = seq.items() if isinstance(seq, Mapping) else seq
        iseq: dict[bytes, list[bytes]] = {}
        # normkey() only sees keys already stored, so keys from seq that differ
        # only in case are mapped to a single spelling here.
        spellings: dict[bytes, bytes] = {}
        for k, v in items:
            key = self._normkey(k)
            key = spellings.setdefault(key.lower(), key)
            iseq.setdefault(key, []).extend(self._normvalue(v))
        dict.update(self, iseq)

    def _normkey(self, key: str | bytes) -> bytes:
        """Normalize key to bytes, matching the case of an existing key if any."""
        key = self._tobytes(key)
        if dict.__contains__(self, key):
            return key
        lower_key = key.lower()
        existing_key: bytes
        for existing_key in dict.keys(self):
            if existing_key.lower() == lower_key:
                return existing_key
        return key

    def normkey(self, key: str | bytes) -> bytes:  # pragma: no cover
        warnings.warn(
            "Headers.normkey() is deprecated",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self._normkey(key)

    def _normvalue(self, value: _RawValue | Iterable[_RawValue]) -> list[bytes]:
        """Normalize values to bytes."""
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

    def normvalue(
        self, value: _RawValue | Iterable[_RawValue]
    ) -> list[bytes]:  # pragma: no cover
        warnings.warn(
            "Headers.normvalue() is deprecated",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self._normvalue(value)

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
            return cast("list[bytes]", dict.__getitem__(self, self._normkey(key)))[-1]
        except IndexError:
            return None

    def get(self, key: str | bytes, def_val: Any = None) -> bytes | None:
        """Return the last value of the *key* header, or *def_val* as
        :class:`bytes` if the header is missing or set to ``None``."""
        values = cast("list[bytes] | None", dict.get(self, self._normkey(key)))
        if not values:
            # The header is missing, or it was set to None so that it is not
            # sent; neither has a value to return.
            values = self._normvalue(def_val)
        return values[-1] if values else None

    def getlist(
        self, key: str | bytes, def_val: _RawValue | Iterable[_RawValue] | None = None
    ) -> list[bytes]:
        """Return the values of the *key* header as a list of :class:`bytes`.

        If the header is missing, return *def_val* as such a list instead, or
        an empty list if *def_val* is ``None``.
        """
        try:
            return cast("list[bytes]", dict.__getitem__(self, self._normkey(key)))
        except KeyError:
            if def_val is not None:
                return self._normvalue(def_val)
            return []

    def setlist(self, key: str | bytes, list_: Iterable[_RawValue]) -> None:
        warnings.warn(
            "Headers.setlist() is deprecated, assign the list instead:"
            " headers[key] = values.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self[key] = list_

    def setlistdefault(
        self, key: str | bytes, default_list: Iterable[_RawValue] = ()
    ) -> Any:
        warnings.warn(
            "Headers.setlistdefault() is deprecated, use setdefault() instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self.setdefault(key, default_list)

    def appendlist(self, key: str | bytes, value: Iterable[_RawValue]) -> None:
        lst = self.getlist(key)
        lst.extend(self._normvalue(value))
        self[key] = lst

    def items(self) -> Iterable[tuple[bytes, list[bytes]]]:  # type: ignore[override]
        return ((k, self.getlist(k)) for k in self.keys())

    def values(self) -> list[bytes | None]:  # type: ignore[override]
        return [
            self[k]
            for k in self.keys()  # pylint: disable=consider-using-dict-items
        ]

    @property
    def raw(self) -> list[tuple[bytes, bytes]]:
        """The headers as ``(name, value)`` pairs of bytes, one per value.

        .. versionadded:: VERSION
        """
        return [(key, value) for key, values in dict.items(self) for value in values]

    def to_string(self) -> bytes:
        """Return the headers as :class:`bytes`, with one ``name: value`` line
        per value and CRLF between lines."""
        return b"\r\n".join(key + b": " + value for key, value in self.raw)

    def to_unicode_dict(self) -> CaseInsensitiveDict:
        warnings.warn(
            "Headers.to_unicode_dict() is deprecated, use to_tuple_list() instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return CaseInsensitiveDict(
            (
                key.decode(self.encoding, errors="replace"),
                b",".join(value).decode(self.encoding, errors="replace"),
            )
            for key, value in self.items()
        )

    def to_tuple_list(self) -> list[tuple[str, str]]:
        """Return headers as a list of ``(key, value)`` tuples.

        Multiple values are represented as multiple tuples with the same key.
        Bytes that cannot be decoded are replaced with U+FFFD. Use :attr:`raw`
        for the exact bytes.
        """
        return [
            (
                key.decode(self.encoding, errors="replace"),
                value.decode(self.encoding, errors="replace"),
            )
            for key, values in self.items()
            for value in values
        ]

    def __copy__(self) -> Self:
        return self.__class__(self)

    copy = __copy__
