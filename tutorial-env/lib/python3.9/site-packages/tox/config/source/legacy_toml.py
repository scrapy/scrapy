from __future__ import annotations

import sys

if sys.version_info >= (3, 11):  # pragma: no cover (py311+)
    import tomllib
else:  # pragma: no cover (py311+)
    import tomli as tomllib


from typing import TYPE_CHECKING

from .ini import IniSource

if TYPE_CHECKING:
    from pathlib import Path


class LegacyToml(IniSource):
    FILENAME = "pyproject.toml"

    def __init__(self, path: Path) -> None:
        if path.name != self.FILENAME or not path.exists():
            raise ValueError
        with path.open("rb") as file_handler:
            toml_content = tomllib.load(file_handler)
        try:
            content = toml_content["tool"]["tox"]["legacy_tox_ini"]
        except KeyError as exc:
            raise ValueError(path) from exc
        super().__init__(path, content=content)


__all__ = ("LegacyToml",)
