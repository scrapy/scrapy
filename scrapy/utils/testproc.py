from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, cast

from twisted.internet.defer import Deferred
from twisted.internet.error import ProcessTerminated
from twisted.internet.protocol import ProcessProtocol

if TYPE_CHECKING:
    from collections.abc import Iterable

    from twisted.python.failure import Failure


class ProcessTest:
    command: str | None = None
    prefix = [sys.executable, "-m", "scrapy.cmdline"]
    cwd = os.getcwd()  # trial chdirs to temp dir

    def execute(
        self,
        args: Iterable[str],
        check_code: bool = True,
        settings: str | None = None,
    ) -> Deferred[TestProcessProtocol]:
        from twisted.internet import reactor

        env = os.environ.copy()
        if settings is not None:
            env["SCRAPY_SETTINGS_MODULE"] = settings
        assert self.command
        cmd = self.prefix + [self.command] + list(args)
        pp = TestProcessProtocol()
        pp.deferred.addCallback(self._process_finished, cmd, check_code)
        reactor.spawnProcess(pp, cmd[0], cmd, env=env, path=self.cwd)
        return pp.deferred

    def _process_finished(
        self, pp: TestProcessProtocol, cmd: list[str], check_code: bool
    ) -> tuple[int, bytes, bytes]:
        if pp.exitcode and check_code:
            msg = f"process {cmd} exit with code {pp.exitcode}"
            msg += f"\n>>> stdout <<<\n{pp.out.decode()}"
            msg += "\n"
            msg += f"\n>>> stderr <<<\n{pp.err.decode()}"
            raise RuntimeError(msg)
        return cast(int, pp.exitcode), pp.out, pp.err


class TestProcessProtocol(ProcessProtocol):
    def __init__(self) -> None:
        self.deferred: Deferred[TestProcessProtocol] = Deferred()
        self.out: bytes = b""
        self.err: bytes = b""
        self.exitcode: int | None = None

    def outReceived(self, data: bytes) -> None:
        self.out += data

    def errReceived(self, data: bytes) -> None:
        self.err += data

    def processEnded(self, status: Failure) -> None:
        self.exitcode = cast(ProcessTerminated, status.value).exitCode
        self.deferred.callback(self)
