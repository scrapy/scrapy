# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from typing import Optional


class Enum:
    group: Optional[str] = None

    def __init__(self, label: str) -> None:
        self.label = label

    def __repr__(self) -> str:
        return f"<{self.group}: {self.label}>"

    def __str__(self) -> str:
        return self.label


class StatusEnum(Enum):
    group = "Status"


OFFLINE = Enum("Offline")
ONLINE = Enum("Online")
AWAY = Enum("Away")


class OfflineError(Exception):
    """The requested action can't happen while offline."""
