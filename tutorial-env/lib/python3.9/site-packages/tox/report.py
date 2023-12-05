"""Handle reporting from within tox."""
from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from io import BytesIO, TextIOWrapper
from pathlib import Path
from threading import Thread, current_thread, enumerate, local
from typing import IO, ClassVar, Iterator, Tuple

from colorama import Fore, Style, init

LEVELS = {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG,
    5: logging.NOTSET,
}

MAX_LEVEL = max(LEVELS.keys())
LOGGER = logging.getLogger()
OutErr = Tuple[TextIOWrapper, TextIOWrapper]


class _LogThreadLocal(local):
    """A thread local variable that inherits values from its parent."""

    _ident_to_data: ClassVar[dict[int | None, str]] = {}

    def __init__(self, out_err: OutErr) -> None:
        self.name = self._ident_to_data.get(getattr(current_thread(), "parent_ident", None), "ROOT")
        self.out_err = out_err

    @staticmethod
    @contextmanager
    def patch_thread() -> Iterator[None]:
        def new_start(self: Thread) -> None:  # need to patch this
            self.parent_ident = current_thread().ident  # type: ignore[attr-defined]
            old_start(self)

        old_start, Thread.start = Thread.start, new_start  # type: ignore[method-assign]
        try:
            yield
        finally:
            Thread.start = old_start  # type: ignore[method-assign]

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

        for ident in self._ident_to_data.keys() - {t.ident for t in enumerate()}:
            self._ident_to_data.pop(ident)
        self._ident_to_data[current_thread().ident] = value

    @contextmanager
    def with_name(self, name: str) -> Iterator[None]:
        previous, self.name = self.name, name
        try:
            yield
        finally:
            self.name = previous

    @contextmanager
    def suspend_out_err(self, yes: bool, out_err: OutErr | None = None) -> Iterator[OutErr]:  # noqa: FBT001
        previous_out, previous_err = self.out_err
        try:
            if yes:
                if out_err is None:  # pragma: no branch
                    out = self._make(f"out-{self.name}", previous_out)
                    err = self._make(f"err-{self.name}", previous_err)
                else:
                    out, err = out_err  # pragma: no cover
                self.out_err = out, err
            yield self.out_err
        finally:
            if yes:
                self.out_err = previous_out, previous_err

    @staticmethod
    def _make(prefix: str, based_of: TextIOWrapper) -> TextIOWrapper:
        return TextIOWrapper(NamedBytesIO(f"{prefix}-{based_of.name}"))


class NamedBytesIO(BytesIO):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name: str = name


class ToxHandler(logging.StreamHandler):  # type: ignore[type-arg] # is generic but at runtime doesn't take a type arg
    # """Controls tox output."""

    def __init__(self, level: int, is_colored: bool, out_err: OutErr) -> None:  # noqa: FBT001
        self._local = _LogThreadLocal(out_err)
        super().__init__(stream=self.stdout)
        if is_colored:
            init()
        self._is_colored = is_colored
        self._setup_level(is_colored, level)

    def _setup_level(self, is_colored: bool, level: int) -> None:  # noqa: FBT001
        self.setLevel(level)
        self._error_formatter = self._get_formatter(logging.ERROR, level, is_colored)
        self._warning_formatter = self._get_formatter(logging.WARNING, level, is_colored)
        self._remaining_formatter = self._get_formatter(logging.INFO, level, is_colored)

    @contextmanager
    def with_context(self, name: str) -> Iterator[None]:
        """
        Set a new tox environment context.

        :param name: the name of the tox environment
        """
        with self._local.with_name(name):
            yield

    @property
    def name(self) -> str:  # type: ignore[override]
        """:return: the current tox environment name"""
        return self._local.name  # pragma: no cover

    @property
    def stdout(self) -> TextIOWrapper:
        """:return: the current standard output"""
        return self._local.out_err[0]

    @property
    def stderr(self) -> TextIOWrapper:
        """:return: the current standard error"""
        return self._local.out_err[1]

    @property  # type: ignore[override]
    def stream(self) -> IO[str]:
        """:return: the current stream to write to (alias for the current standard output)"""
        return self.stdout

    @stream.setter
    def stream(self, value: IO[str]) -> None:
        """Ignore anyone changing this."""

    @contextmanager
    def suspend_out_err(self, yes: bool, out_err: OutErr | None = None) -> Iterator[OutErr]:  # noqa: FBT001
        with self._local.suspend_out_err(yes, out_err) as out_err_res:
            yield out_err_res

    def write_out_err(self, out_err: tuple[bytes, bytes]) -> None:
        # read/write through the buffer as we collect bytes to print bytes (no transcoding needed)
        self.stdout.buffer.write(out_err[0])
        self.stderr.buffer.write(out_err[1])

    @staticmethod
    def _get_formatter(level: int, enabled_level: int, is_colored: bool) -> logging.Formatter:  # noqa: FBT001
        color: int | str = ""
        if is_colored:
            if level >= logging.ERROR:
                color = Fore.RED
            elif level >= logging.WARNING:
                color = Fore.CYAN
            else:
                color = Fore.WHITE

        def _c(val: int) -> str:
            return str(val) if color else ""

        fmt = f"{color} %(message)s{_c(Style.RESET_ALL)}"
        if enabled_level <= logging.DEBUG:
            fmt = (
                f"{_c(Fore.GREEN)} %(relativeCreated)d %(levelname).1s{_c(Style.RESET_ALL)}{fmt}{_c(Style.DIM)}"
                f" [%(pathname)s:%(lineno)d]{_c(Style.RESET_ALL)}"
            )
        fmt = f"{_c(Style.BRIGHT)}{_c(Fore.MAGENTA)}%(env_name)s:{_c(Style.RESET_ALL)}" + fmt
        return logging.Formatter(fmt)

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        # shorten the pathname to start from within the site-packages folder
        record.env_name = "root" if self._local.name is None else self._local.name
        basename = str(Path(record.pathname).parent)
        len_sys_path_match = max((len(p) for p in sys.path if basename.startswith(p)), default=-1)
        record.pathname = record.pathname[len_sys_path_match + 1 :]

        if record.levelno >= logging.ERROR:
            return self._error_formatter.format(record)
        if record.levelno >= logging.WARNING:
            if self._is_colored and record.msg == "%s%s> %s" and record.args:
                record.msg = f"%s{Style.NORMAL}%s{Style.DIM}>{Style.RESET_ALL} %s"
            return self._warning_formatter.format(record)
        return self._remaining_formatter.format(record)

    @staticmethod
    @contextmanager
    def patch_thread() -> Iterator[None]:
        with _LogThreadLocal.patch_thread():
            yield

    def update_verbosity(self, verbosity: int) -> None:
        level = _get_level(verbosity)
        LOGGER.setLevel(level)
        self._setup_level(self._is_colored, level)


def setup_report(verbosity: int, is_colored: bool) -> ToxHandler:  # noqa: FBT001
    _clean_handlers(LOGGER)
    level = _get_level(verbosity)
    LOGGER.setLevel(level)
    for name in ("distlib.util", "filelock"):
        logger = logging.getLogger(name)
        logger.disabled = True
    out_err: OutErr = (sys.stdout, sys.stderr)  # type: ignore[assignment]
    handler = ToxHandler(level, is_colored, out_err)
    LOGGER.addHandler(handler)
    logging.debug("setup logging to %s on pid %s", logging.getLevelName(level), os.getpid())
    return handler


def _get_level(verbosity: int) -> int:
    return LEVELS[min(verbosity, MAX_LEVEL)]


def _clean_handlers(log: logging.Logger) -> None:
    for log_handler in list(log.handlers):  # remove handlers of libraries
        log.removeHandler(log_handler)


class HandledError(RuntimeError):
    """Error that has been handled so no need for stack trace."""
