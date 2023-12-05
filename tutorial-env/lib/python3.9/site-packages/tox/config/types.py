from __future__ import annotations

from collections import OrderedDict
from typing import Iterator, Sequence

from tox.execute.request import shell_cmd


class Command:
    """A command to execute."""

    def __init__(self, args: list[str]) -> None:
        """
        Create a new command to execute.

        :param args: the command line arguments (first value can be ``-`` to indicate ignore the exit code)
        """
        self.ignore_exit_code: bool = args[0] == "-"  #: a flag indicating if the exit code should be ignored
        self.args: list[str] = args[1:] if self.ignore_exit_code else args  #: the command line arguments

    def __repr__(self) -> str:
        return f"{type(self).__name__}(args={(['-'] if self.ignore_exit_code else [])+ self.args!r})"

    def __eq__(self, other: object) -> bool:
        return type(self) == type(other) and (self.args, self.ignore_exit_code) == (
            other.args,  # type: ignore[attr-defined]
            other.ignore_exit_code,  # type: ignore[attr-defined]
        )

    def __ne__(self, other: object) -> bool:
        return not (self == other)

    @property
    def shell(self) -> str:
        """:return: a shell representation of the command (platform dependent)"""
        return shell_cmd(self.args)


class EnvList:
    """A tox environment list."""

    def __init__(self, envs: Sequence[str]) -> None:
        """
        Crate a new tox environment list.

        :param envs: the list of tox environments
        """
        self.envs = list(OrderedDict((e, None) for e in envs).keys())

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.envs!r})"

    def __eq__(self, other: object) -> bool:
        return type(self) == type(other) and self.envs == other.envs  # type: ignore[attr-defined]

    def __ne__(self, other: object) -> bool:
        return not (self == other)

    def __iter__(self) -> Iterator[str]:
        """:return: iterator that goes through the defined env-list"""
        return iter(self.envs)


__all__ = (
    "Command",
    "EnvList",
)
