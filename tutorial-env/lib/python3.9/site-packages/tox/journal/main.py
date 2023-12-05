"""Generate json report of a tox run."""
from __future__ import annotations

import socket
import sys
from typing import Any

from tox.version import version

from .env import EnvJournal


class Journal:
    """The result of a tox session."""

    def __init__(self, enabled: bool) -> None:  # noqa: FBT001
        self._enabled = enabled
        self._content: dict[str, Any] = {}
        self._env: dict[str, EnvJournal] = {}

        if self._enabled:
            self._content.update(
                {
                    "reportversion": "1",
                    "toxversion": version,
                    "platform": sys.platform,
                    "host": socket.getfqdn(),
                },
            )

    def get_env_journal(self, name: str) -> EnvJournal:
        """Return the env log of an environment (create on first call)."""
        if name not in self._env:
            env = EnvJournal(self._enabled, name)
            self._env[name] = env
        return self._env[name]

    @property
    def content(self) -> dict[str, Any]:
        test_env_journals: dict[str, Any] = {}
        for name, value in self._env.items():
            test_env_journals[name] = value.content
        if test_env_journals:
            self._content["testenvs"] = test_env_journals
        return self._content

    def __bool__(self) -> bool:
        return self._enabled


__all__ = ("Journal",)
