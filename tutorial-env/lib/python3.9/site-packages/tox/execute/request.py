"""Module declaring a command execution request."""
from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import Sequence


class StdinSource(Enum):
    OFF = 0  #: input disabled
    USER = 1  #: input via the standard input
    API = 2  #: input via programmatic access

    @staticmethod
    def user_only() -> StdinSource:
        """:return: ``USER`` if the standard input is tty type else ``OFF``"""
        return StdinSource.USER if sys.stdin.isatty() else StdinSource.OFF


class ExecuteRequest:
    """Defines a commands execution request."""

    def __init__(  # noqa: PLR0913
        self,
        cmd: Sequence[str | Path],
        cwd: Path,
        env: dict[str, str],
        stdin: StdinSource,
        run_id: str,
        allow: list[str] | None = None,
    ) -> None:
        """
        Create a new execution request.

        :param cmd: the command to run
        :param cwd: the current working directory
        :param env: the environment variables
        :param stdin: the type of standard input allowed
        :param run_id: an id to identify this run
        """
        if len(cmd) == 0:
            msg = "cannot execute an empty command"
            raise ValueError(msg)
        self.cmd: list[str] = [str(i) for i in cmd]  #: the command to run
        self.cwd = cwd  #: the working directory to use
        self.env = env  #: the environment variables to use
        self.stdin = stdin  #: the type of standard input interaction allowed
        self.run_id = run_id  #: an id to identify this run
        if allow is not None and "*" in allow:
            allow = None  # if we allow everything we can just disable the check
        self.allow = allow

    @property
    def shell_cmd(self) -> str:
        """:return: the command to run as a shell command"""
        try:
            exe = str(Path(self.cmd[0]).relative_to(self.cwd))
        except ValueError:
            exe = self.cmd[0]
        _cmd = [exe]
        _cmd.extend(self.cmd[1:])
        return shell_cmd(_cmd)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(cmd={self.cmd!r}, cwd={self.cwd!r}, env=..., stdin={self.stdin!r})"


def shell_cmd(cmd: Sequence[str]) -> str:
    if sys.platform == "win32":  # pragma: win32 cover
        from subprocess import list2cmdline

        return list2cmdline(tuple(str(x) for x in cmd))
    # pragma: win32 no cover
    from shlex import quote as shlex_quote

    return " ".join(shlex_quote(str(x)) for x in cmd)


__all__ = (
    "StdinSource",
    "ExecuteRequest",
    "shell_cmd",
)
