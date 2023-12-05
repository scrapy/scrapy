from __future__ import annotations

from typing import TYPE_CHECKING

from .ini import IniSource
from .ini_section import IniSection

if TYPE_CHECKING:
    from pathlib import Path


class SetupCfg(IniSource):
    """Configuration sourced from a tox.ini file."""

    CORE_SECTION = IniSection("tox", "tox")
    FILENAME = "setup.cfg"

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        if not self._parser.has_section(self.CORE_SECTION.key):
            raise ValueError


__all__ = ("SetupCfg",)
