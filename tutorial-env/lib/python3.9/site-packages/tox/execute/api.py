"""Abstract base API for executing commands within tox environments."""
from __future__ import annotations

import logging
import sys
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Iterator, NoReturn, Sequence, cast

from colorama import Fore

from .request import ExecuteRequest, StdinSource
from .stream import SyncWrite

if TYPE_CHECKING:
    from types import TracebackType

    from tox.report import OutErr
    from tox.tox_env.api import ToxEnv

ContentHandler = Callable[[bytes], None]
Executor = Callable[[ExecuteRequest, ContentHandler, ContentHandler], int]
LOGGER = logging.getLogger(__name__)


class ExecuteOptions:
    def __init__(self, env: ToxEnv) -> None:
        self._env = env

    @classmethod
    def register_conf(cls, env: ToxEnv) -> None:
        env.conf.add_config(
            keys=["suicide_timeout"],
            desc="timeout to allow process to exit before sending SIGINT",
            of_type=float,
            default=0.0,
        )
        env.conf.add_config(
            keys=["interrupt_timeout"],
            desc="timeout before sending SIGTERM after SIGINT",
            of_type=float,
            default=0.3,
        )
        env.conf.add_config(
            keys=["terminate_timeout"],
            desc="timeout before sending SIGKILL after SIGTERM",
            of_type=float,
            default=0.2,
        )

    @property
    def suicide_timeout(self) -> float:
        return cast(float, self._env.conf["suicide_timeout"])

    @property
    def interrupt_timeout(self) -> float:
        return cast(float, self._env.conf["interrupt_timeout"])

    @property
    def terminate_timeout(self) -> float:
        return cast(float, self._env.conf["terminate_timeout"])


class ExecuteStatus(ABC):
    def __init__(self, options: ExecuteOptions, out: SyncWrite, err: SyncWrite) -> None:
        self.outcome: Outcome | None = None
        self.options = options
        self._out = out
        self._err = err

    @property
    @abstractmethod
    def exit_code(self) -> int | None:
        raise NotImplementedError

    @abstractmethod
    def wait(self, timeout: float | None = None) -> int | None:
        raise NotImplementedError

    @abstractmethod
    def write_stdin(self, content: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def interrupt(self) -> None:
        raise NotImplementedError

    def set_out_err(self, out: SyncWrite, err: SyncWrite) -> tuple[SyncWrite, SyncWrite]:
        res = self._out, self._err
        self._out, self._err = out, err
        return res

    @property
    def out(self) -> bytearray:
        return self._out.content

    @property
    def err(self) -> bytearray:
        return self._err.content

    @property
    def metadata(self) -> dict[str, Any]:
        return {}


class Execute(ABC):
    """Abstract API for execution of a tox environment."""

    _option_class: type[ExecuteOptions] = ExecuteOptions

    def __init__(self, colored: bool) -> None:  # noqa: FBT001
        self._colored = colored

    @contextmanager
    def call(
        self,
        request: ExecuteRequest,
        show: bool,  # noqa: FBT001
        out_err: OutErr,
        env: ToxEnv,
    ) -> Iterator[ExecuteStatus]:
        start = time.monotonic()
        try:
            # collector is what forwards the content from the file streams to the standard streams
            out, err = out_err[0].buffer, out_err[1].buffer
            out_sync = SyncWrite(out.name, out if show else None)
            err_sync = SyncWrite(err.name, err if show else None, Fore.RED if self._colored else None)
            with out_sync, err_sync:
                instance = self.build_instance(request, self._option_class(env), out_sync, err_sync)
                with instance as status:
                    yield status
                exit_code = status.exit_code
        finally:
            end = time.monotonic()
        status.outcome = Outcome(
            request,
            show,
            exit_code,
            out_sync.text,
            err_sync.text,
            start,
            end,
            instance.cmd,
            status.metadata,
        )

    @abstractmethod
    def build_instance(
        self,
        request: ExecuteRequest,
        options: ExecuteOptions,
        out: SyncWrite,
        err: SyncWrite,
    ) -> ExecuteInstance:
        raise NotImplementedError

    @classmethod
    def register_conf(cls, env: ToxEnv) -> None:
        cls._option_class.register_conf(env)


class ExecuteInstance(ABC):
    """An instance of a command execution."""

    def __init__(self, request: ExecuteRequest, options: ExecuteOptions, out: SyncWrite, err: SyncWrite) -> None:
        self.request = request
        self.options = options
        self._out = out
        self._err = err

    @property
    def out_handler(self) -> ContentHandler:
        return self._out.handler

    @property
    def err_handler(self) -> ContentHandler:
        return self._err.handler

    @abstractmethod
    def __enter__(self) -> ExecuteStatus:
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def cmd(self) -> Sequence[str]:
        raise NotImplementedError


class Outcome:
    """Result of a command execution."""

    OK = 0

    def __init__(  # noqa: PLR0913
        self,
        request: ExecuteRequest,
        show_on_standard: bool,  # noqa: FBT001
        exit_code: int | None,
        out: str,
        err: str,
        start: float,
        end: float,
        cmd: Sequence[str],
        metadata: dict[str, Any],
    ) -> None:
        """
        Create a new execution outcome.

        :param request: the execution request
        :param show_on_standard: a flag indicating if the execution was shown on stdout/stderr
        :param exit_code: the exit code for the execution
        :param out: the standard output of the execution
        :param err: the standard error of the execution
        :param start: a timer sample for the start of the execution
        :param end: a timer sample for the end of the execution
        :param cmd: the command as executed
        :param metadata: additional metadata attached to the execution
        """
        self.request = request  #: the execution request
        self.show_on_standard = show_on_standard  #: a flag indicating if the execution was shown on stdout/stderr
        self.exit_code = exit_code  #: the exit code for the execution
        self.out = out  #: the standard output of the execution
        self.err = err  #: the standard error of the execution
        self.start = start  #: a timer sample for the start of the execution
        self.end = end  #: a timer sample for the end of the execution
        self.cmd = cmd  #: the command as executed
        self.metadata = metadata  #: additional metadata attached to the execution

    def __bool__(self) -> bool:
        return self.exit_code == self.OK

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}: exit {self.exit_code} in {self.elapsed:.2f} seconds"
            f" for {self.request.shell_cmd}"
        )

    def assert_success(self) -> None:
        """Assert that the execution succeeded."""
        if self.exit_code is not None and self.exit_code != self.OK:
            self._assert_fail()
        self.log_run_done(logging.INFO)

    def _assert_fail(self) -> NoReturn:
        if self.show_on_standard is False:
            if self.out:
                sys.stdout.write(self.out)
                if not self.out.endswith("\n"):
                    sys.stdout.write("\n")
            if self.err:
                sys.stderr.write(Fore.RED)
                sys.stderr.write(self.err)
                sys.stderr.write(Fore.RESET)
                if not self.err.endswith("\n"):
                    sys.stderr.write("\n")
        self.log_run_done(logging.CRITICAL)
        raise SystemExit(self.exit_code)

    def log_run_done(self, lvl: int) -> None:
        """
        Log that the run was done.

        :param lvl: the level on what to log as interpreted by :func:`logging.log`
        """
        req = self.request
        metadata = ""
        if self.metadata:
            metadata = f" {', '.join(f'{k}={v}' for k, v in self.metadata.items())}"
        LOGGER.log(
            lvl,
            "exit %s (%.2f seconds) %s> %s%s",
            self.exit_code,
            self.elapsed,
            req.cwd,
            req.shell_cmd,
            metadata,
        )

    @property
    def elapsed(self) -> float:
        """:return: time the execution took in seconds"""
        return self.end - self.start

    def out_err(self) -> tuple[str, str]:
        """:return: a tuple of the standard output and standard error"""
        return self.out, self.err


__all__ = (
    "ContentHandler",
    "Outcome",
    "Execute",
    "ExecuteInstance",
    "ExecuteOptions",
    "ExecuteStatus",
    "StdinSource",
)
