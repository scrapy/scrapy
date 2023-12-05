"""Record information about tox environments."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tox.execute import Outcome


class EnvJournal:
    """Report the status of a tox environment."""

    def __init__(self, enabled: bool, name: str) -> None:  # noqa: FBT001
        self._enabled = enabled
        self.name = name
        self._content: dict[str, Any] = {}
        self._executes: list[tuple[str, Outcome]] = []

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Add a new entry under key into the event journal.

        :param key: the key under what to add the data
        :param value: the data to add
        """
        self._content[key] = value

    def __bool__(self) -> bool:
        """:return: a flag indicating if the event journal is on or not"""
        return self._enabled

    def add_execute(self, outcome: Outcome, run_id: str) -> None:
        """
        Add a command execution to the journal.

        :param outcome: the execution outcome
        :param run_id: the execution id
        """
        self._executes.append((run_id, outcome))

    @property
    def content(self) -> dict[str, Any]:
        """:return: the env journal content (merges explicit keys and execution commands)"""
        tests: list[dict[str, Any]] = []
        setup: list[dict[str, Any]] = []
        for run_id, outcome in self._executes:
            one = {
                "command": outcome.cmd,
                "output": outcome.out,
                "err": outcome.err,
                "retcode": outcome.exit_code,
                "elapsed": outcome.elapsed,
                "show_on_standard": outcome.show_on_standard,
                "run_id": run_id,
                "start": outcome.start,
                "end": outcome.end,
            }
            if run_id.startswith(("commands", "build")):
                tests.append(one)
            else:
                setup.append(one)
        if tests:
            self["test"] = tests
        if setup:
            self["setup"] = setup
        return self._content


__all__ = ("EnvJournal",)
