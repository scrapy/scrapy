from __future__ import annotations

from .ini import IniSource


class ToxIni(IniSource):
    """Configuration sourced from a tox.ini file."""

    FILENAME = "tox.ini"


__all__ = ("ToxIni",)
