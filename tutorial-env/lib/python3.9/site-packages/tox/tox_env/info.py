"""
Declare and handle the tox env info file (a file at the root of every tox environment that contains information about
the status of the tox environment - python version of the environment, installed packages, etc.).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from pathlib import Path


class Info:
    """Stores metadata about the tox environment."""

    def __init__(self, path: Path) -> None:
        self._path = path / ".tox-info.json"
        try:
            value = json.loads(self._path.read_text())
        except (ValueError, OSError):
            value = {}
        self._content = value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(path={self._path})"

    @contextmanager
    def compare(
        self,
        value: Any,
        section: str,
        sub_section: str | None = None,
    ) -> Iterator[tuple[bool, Any | None]]:
        """
        Compare new information with the existing one and update if differs.

        :param value: the value stored
        :param section: the primary key of the information
        :param sub_section: the secondary key of the information
        :return: a tuple where the first value is if it differs and the second is the old value
        """
        old = self._content.get(section)
        if sub_section is not None and old is not None:
            old = old.get(sub_section)

        if old == value:
            yield True, old
        else:
            yield False, old
            # if no exception thrown update
            if sub_section is None:
                self._content[section] = value
            elif self._content.get(section) is None:
                self._content[section] = {sub_section: value}
            else:
                self._content[section][sub_section] = value
            self._write()

    def reset(self) -> None:
        self._content = {}

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._content, indent=2))


__all__ = ("Info",)
