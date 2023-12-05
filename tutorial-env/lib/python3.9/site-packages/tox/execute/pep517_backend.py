"""A executor that reuses a single subprocess for all backend calls (saving on python startup/import overhead)."""
from __future__ import annotations

import time
from subprocess import TimeoutExpired
from threading import Lock
from typing import TYPE_CHECKING, Sequence

from pyproject_api import BackendFailed

from tox.execute import ExecuteRequest
from tox.execute.api import Execute, ExecuteInstance, ExecuteOptions, ExecuteStatus
from tox.execute.local_sub_process import LocalSubProcessExecuteInstance
from tox.execute.request import StdinSource
from tox.execute.stream import SyncWrite

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType


class LocalSubProcessPep517Executor(Execute):
    """Executor holding the backend process."""

    def __init__(self, colored: bool, cmd: Sequence[str], env: dict[str, str], cwd: Path) -> None:  # noqa: FBT001
        super().__init__(colored)
        self.cmd = cmd
        self.env = env
        self.cwd = cwd
        self._local_execute: tuple[LocalSubProcessExecuteInstance, ExecuteStatus] | None = None
        self._exc: Exception | None = None
        self.is_alive: bool = False

    def build_instance(
        self,
        request: ExecuteRequest,
        options: ExecuteOptions,
        out: SyncWrite,
        err: SyncWrite,
    ) -> ExecuteInstance:
        return LocalSubProcessPep517ExecuteInstance(request, options, out, err, self.local_execute(options))

    def local_execute(self, options: ExecuteOptions) -> tuple[LocalSubProcessExecuteInstance, ExecuteStatus]:
        if self._exc is not None:
            raise self._exc
        if self._local_execute is None:
            request = ExecuteRequest(cmd=self.cmd, cwd=self.cwd, env=self.env, stdin=StdinSource.API, run_id="pep517")

            instance = LocalSubProcessExecuteInstance(
                request=request,
                options=options,
                out=SyncWrite(name="pep517-out", target=None, color=None),  # not enabled no need to enter/exit
                err=SyncWrite(name="pep517-err", target=None, color=None),  # not enabled no need to enter/exit
                on_exit_drain=False,
            )
            status = instance.__enter__()
            self._local_execute = instance, status
            while True:
                if b"started backend " in status.out:
                    self.is_alive = True
                    break
                if b"failed to start backend" in status.err:
                    from tox.tox_env.python.virtual_env.package.pyproject import ToxBackendFailed

                    failure = BackendFailed(
                        result={
                            "code": -5,
                            "exc_type": "FailedToStart",
                            "exc_msg": "could not start backend",
                        },
                        out=status.out.decode(),
                        err=status.err.decode(),
                    )
                    self._exc = ToxBackendFailed(failure)
                    raise self._exc
                time.sleep(0.01)  # wait a short while for the output to populate
        return self._local_execute

    @staticmethod
    def _handler(into: bytearray, content: bytes) -> None:
        """Ignore content generated."""
        into.extend(content)  # pragma: no cover

    def close(self) -> None:
        if self._local_execute is not None:  # pragma: no branch
            execute, status = self._local_execute
            execute.__exit__(None, None, None)
            if execute.process is not None and execute.process.returncode is None:  # pragma: no cover
                try:  # pragma: no cover
                    execute.process.wait(timeout=0.1)  # pragma: no cover
                except TimeoutExpired:  # pragma: no cover
                    execute.process.terminate()  # pragma: no cover  # if does not stop on its own kill it
        self.is_alive = False


class LocalSubProcessPep517ExecuteInstance(ExecuteInstance):
    """A backend invocation."""

    def __init__(  # noqa: PLR0913
        self,
        request: ExecuteRequest,
        options: ExecuteOptions,
        out: SyncWrite,
        err: SyncWrite,
        instance_status: tuple[LocalSubProcessExecuteInstance, ExecuteStatus],
    ) -> None:
        super().__init__(request, options, out, err)
        self._instance, self._status = instance_status
        self._lock = Lock()

    @property
    def cmd(self) -> Sequence[str]:
        return self._instance.cmd

    def __enter__(self) -> ExecuteStatus:
        self._lock.acquire()
        self._swap_out_err()
        return self._status

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._swap_out_err()
        self._lock.release()

    def _swap_out_err(self) -> None:
        out, err = self._out, self._err
        # update status to see the newly collected content
        self._out, self._err = self._instance.set_out_err(out, err)
        # update the thread out/err
        self._status.set_out_err(out, err)
