from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sys

    if sys.version_info >= (3, 11):  # pragma: no cover (py311+)
        from typing import Self
    else:  # pragma: no cover (<py311)
        from typing_extensions import Self


class Section:
    """tox configuration section."""

    SEP = ":"  #: string used to separate the prefix and the section in the key

    def __init__(self, prefix: str | None, name: str) -> None:
        self._prefix = prefix
        self._name = name

    @classmethod
    def from_key(cls: type[Self], key: str) -> Self:
        """
        Create a section from a section key.

        :param key: the section key
        :return: the constructed section
        """
        sep_at = key.find(cls.SEP)
        if sep_at == -1:
            prefix, name = None, key
        else:
            prefix, name = key[:sep_at], key[sep_at + 1 :]
        return cls(prefix, name)

    @property
    def prefix(self) -> str | None:
        """:return: the prefix of the section"""
        return self._prefix

    @property
    def name(self) -> str:
        """:return: the name of the section"""
        return self._name

    @property
    def key(self) -> str:
        """:return: the section key"""
        return self.SEP.join(i for i in (self._prefix, self._name) if i is not None)

    def __str__(self) -> str:
        return self.key

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(prefix={self._prefix!r}, name={self._name!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and (self._prefix, self._name) == (
            other._prefix,
            other.name,
        )


__all__ = [
    "Section",
]
