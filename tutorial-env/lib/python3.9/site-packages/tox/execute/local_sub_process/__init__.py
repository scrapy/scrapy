"""Execute that runs on local file system via subprocess-es."""
from __future__ import annotations

import fnmatch
import logging
import os
import shutil
import sys
from subprocess import DEVNULL, PIPE, TimeoutExpired
from typing import TYPE_CHECKING, Any, Generator, Sequence

from tox.execute.api import Execute, ExecuteInstance, ExecuteOptions, ExecuteStatus
from tox.execute.request import ExecuteRequest, StdinSource
from tox.execute.util import shebang
from tox.tox_env.errors import Fail

if TYPE_CHECKING:
    import io
    from types import TracebackType

    from tox.execute.stream import SyncWrite

# mypy: warn-unused-ignores=false

if sys.platform == "win32":  # explicit check for mypy # pragma: win32 cover
    # needs stdin/stdout handlers backed by overlapped IO
    if TYPE_CHECKING:  # the typeshed libraries don't contain this, so replace it with normal one
        from subprocess import Popen
    else:
        from asyncio.windows_utils import Popen
    from signal import CTRL_C_EVENT as SIG_INTERRUPT
    from signal import SIGTERM

    from .read_via_thread_windows import ReadViaThreadWindows as ReadViaThread

else:  # pragma: win32 no cover
    from signal import SIGINT as SIG_INTERRUPT
    from signal import SIGKILL, SIGTERM
    from subprocess import Popen

    from .read_via_thread_unix import ReadViaThreadUnix as ReadViaThread


IS_WIN = sys.platform == "win32"


class LocalSubProcessExecutor(Execute):
    def build_instance(
        self,
        request: ExecuteRequest,
        options: ExecuteOptions,
        out: SyncWrite,
        err: SyncWrite,
    ) -> ExecuteInstance:
        return LocalSubProcessExecuteInstance(request, options, out, err)


class LocalSubprocessExecuteStatus(ExecuteStatus):
    def __init__(self, options: ExecuteOptions, out: SyncWrite, err: SyncWrite, process: Popen[bytes]) -> None:
        self._process: Popen[bytes] = process
        super().__init__(options, out, err)
        self._interrupted = False

    @property
    def exit_code(self) -> int | None:
        # need to poll here, to make sure the returncode we get is current
        self._process.poll()
        return self._process.returncode

    def interrupt(self) -> None:
        self._interrupted = True
        if self._process is not None:  # pragma: no branch
            # A three level stop mechanism for children - INT -> TERM -> KILL
            # communicate will wait for the app to stop, and then drain the standard streams and close them
            to_pid, host_pid = self._process.pid, os.getpid()
            msg = "requested interrupt of %d from %d, activate in %.2f"
            logging.warning(msg, to_pid, host_pid, self.options.suicide_timeout)
            if self.wait(self.options.suicide_timeout) is None:  # still alive -> INT
                # on Windows everyone in the same process group, so they got the message
                if sys.platform != "win32":  # pragma: win32 cover
                    msg = "send signal %s to %d from %d with timeout %.2f"
                    logging.warning(msg, f"SIGINT({SIG_INTERRUPT})", to_pid, host_pid, self.options.interrupt_timeout)
                    self._process.send_signal(SIG_INTERRUPT)
                if self.wait(self.options.interrupt_timeout) is None:  # still alive -> TERM # pragma: no branch
                    terminate_output = self.options.terminate_timeout
                    logging.warning(msg, f"SIGTERM({SIGTERM})", to_pid, host_pid, terminate_output)
                    self._process.terminate()
                    # Windows terminate is UNIX kill
                    if sys.platform != "win32" and self.wait(terminate_output) is None:  # pragma: no branch
                        logging.warning(msg[:-18], f"SIGKILL({SIGKILL})", to_pid, host_pid)
                        self._process.kill()  # still alive -> KILL
                    self.wait()  # unconditional wait as kill should soon bring down the process
                logging.warning("interrupt finished with success")
            else:  # pragma: no cover # difficult to test, process must die just as it's being interrupted
                logging.warning("process already dead with %s within %s", self._process.returncode, host_pid)

    def wait(self, timeout: float | None = None) -> int | None:
        try:  # note wait in general might deadlock if output large, but we drain in background threads so not an issue
            return self._process.wait(timeout=timeout)
        except TimeoutExpired:
            return None

    def write_stdin(self, content: str) -> None:
        stdin = self._process.stdin
        if stdin is None:  # pragma: no branch
            return  # pragma: no cover
        bytes_content = content.encode()
        try:
            if sys.platform == "win32":  # explicit check for mypy  # pragma: win32 cover
                # on Windows we have a PipeHandle object here rather than a file stream
                import _overlapped  # type: ignore[import]

                ov = _overlapped.Overlapped(0)
                ov.WriteFile(stdin.handle, bytes_content)  # type: ignore[attr-defined]
                result = ov.getresult(10)  # wait up to 10ms to perform the operation
                if result != len(bytes_content):
                    msg = f"failed to write to {stdin!r}"
                    raise RuntimeError(msg)
            else:
                stdin.write(bytes_content)
                stdin.flush()
        except OSError:  # pragma: no cover
            if self._interrupted:  # pragma: no cover
                pass  # pragma: no cover  # if the process was asked to exit in the meantime ignore write errors
            raise  # pragma: no cover

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(pid={self._process.pid}, returncode={self._process.returncode!r})"

    @property
    def metadata(self) -> dict[str, Any]:
        return {"pid": self._process.pid} if self._process.pid else {}


class LocalSubprocessExecuteFailedStatus(ExecuteStatus):
    def __init__(self, options: ExecuteOptions, out: SyncWrite, err: SyncWrite, exit_code: int | None) -> None:
        super().__init__(options, out, err)
        self._exit_code = exit_code

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    def wait(self, timeout: float | None = None) -> int | None:  # noqa: ARG002
        return self._exit_code  # pragma: no cover

    def write_stdin(self, content: str) -> None:
        """Cannot write."""

    def interrupt(self) -> None:
        return None  # pragma: no cover # nothing running so nothing to interrupt


class LocalSubProcessExecuteInstance(ExecuteInstance):
    def __init__(  # noqa: PLR0913
        self,
        request: ExecuteRequest,
        options: ExecuteOptions,
        out: SyncWrite,
        err: SyncWrite,
        on_exit_drain: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        super().__init__(request, options, out, err)
        self.process: Popen[bytes] | None = None
        self._cmd: list[str] | None = None
        self._read_stderr: ReadViaThread | None = None
        self._read_stdout: ReadViaThread | None = None
        self._on_exit_drain = on_exit_drain

    @property
    def cmd(self) -> Sequence[str]:
        if self._cmd is None:
            base = self.request.cmd[0]
            executable = shutil.which(base, path=self.request.env["PATH"])
            if executable is None:
                cmd = self.request.cmd  # if failed to find leave as it is
            else:
                if self.request.allow is not None:
                    for allow in self.request.allow:
                        # 1. allow matches just the original name of the executable
                        # 2. allow matches the entire resolved path
                        if fnmatch.fnmatch(self.request.cmd[0], allow) or fnmatch.fnmatch(executable, allow):
                            break
                    else:
                        msg = f"{base} (resolves to {executable})" if base == executable else base
                        msg = f"{msg} is not allowed, use allowlist_externals to allow it"
                        raise Fail(msg)
                cmd = [executable]
                if sys.platform != "win32" and self.request.env.get("TOX_LIMITED_SHEBANG", "").strip():
                    shebang_line = shebang(executable)
                    if shebang_line:
                        cmd = [*shebang_line, executable]
                cmd.extend(self.request.cmd[1:])
            self._cmd = cmd
        return self._cmd

    def __enter__(self) -> ExecuteStatus:
        # adjust sub-process terminal size
        columns, lines = shutil.get_terminal_size(fallback=(-1, -1))
        if columns != -1:  # pragma: no branch
            self.request.env.setdefault("COLUMNS", str(columns))
        if lines != -1:  # pragma: no branch
            self.request.env.setdefault("LINES", str(lines))

        stdout, stderr = self.get_stream_file_no("stdout"), self.get_stream_file_no("stderr")
        try:
            self.process = process = Popen(
                self.cmd,  # noqa: S603
                stdout=next(stdout),
                stderr=next(stderr),
                stdin={StdinSource.USER: None, StdinSource.OFF: DEVNULL, StdinSource.API: PIPE}[self.request.stdin],
                cwd=str(self.request.cwd),
                env=self.request.env,
            )
        except OSError as exception:
            return LocalSubprocessExecuteFailedStatus(self.options, self._out, self._err, exception.errno)

        status = LocalSubprocessExecuteStatus(self.options, self._out, self._err, process)
        drain, pid = self._on_exit_drain, self.process.pid
        self._read_stderr = ReadViaThread(stderr.send(process), self.err_handler, name=f"err-{pid}", drain=drain)
        self._read_stderr.__enter__()
        self._read_stdout = ReadViaThread(stdout.send(process), self.out_handler, name=f"out-{pid}", drain=drain)
        self._read_stdout.__enter__()

        if sys.platform == "win32":  # explicit check for mypy:  # pragma: win32 cover
            process.stderr.read = self._read_stderr._drain_stream  # type: ignore[assignment,union-attr]  # noqa: SLF001
            process.stdout.read = self._read_stdout._drain_stream  # type: ignore[assignment,union-attr]  # noqa: SLF001
        return status

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._read_stderr is not None:
            self._read_stderr.__exit__(exc_type, exc_val, exc_tb)
        if self._read_stdout is not None:
            self._read_stdout.__exit__(exc_type, exc_val, exc_tb)
        if self.process is not None:  # cleanup the file handlers
            for stream in (self.process.stdout, self.process.stderr, self.process.stdin):
                if stream is not None and not getattr(stream, "closed", False):
                    try:
                        stream.close()
                    except OSError as exc:  # pragma: no cover
                        logging.warning("error while trying to close %r with %r", stream, exc)  # pragma: no cover

    @staticmethod
    def get_stream_file_no(key: str) -> Generator[int, Popen[bytes], None]:
        allocated_pty = _pty(key)
        if allocated_pty is not None:
            main_fd, child_fd = allocated_pty
            yield child_fd
            os.close(child_fd)  # close the child process pipe
            yield main_fd
        else:
            process = yield PIPE
            stream = getattr(process, key)
            if sys.platform == "win32":  # explicit check for mypy # pragma: win32 cover
                yield stream.handle
            else:
                yield stream.name

    def set_out_err(self, out: SyncWrite, err: SyncWrite) -> tuple[SyncWrite, SyncWrite]:
        prev = self._out, self._err
        if self._read_stdout is not None:  # pragma: no branch
            self._read_stdout.handler = out.handler
        if self._read_stderr is not None:  # pragma: no branch
            self._read_stderr.handler = err.handler
        return prev


def _pty(key: str) -> tuple[int, int] | None:
    """
    Allocate a virtual terminal (pty) for a subprocess.

    A virtual terminal allows a process to perform syscalls that fetch attributes related to the tty,
    for example to determine whether to use colored output or enter interactive mode.

    The termios attributes of the controlling terminal stream will be copied to the allocated pty.

    :param key: The stream to copy attributes from. Either "stdout" or "stderr".
    :return: (main_fd, child_fd) of an allocated pty; or None on error or if unsupported (win32).
    """
    if sys.platform == "win32":  # explicit check for mypy # pragma: win32 cover
        return None

    stream: io.TextIOWrapper = getattr(sys, key)

    # when our current stream is a tty, emulate pty for the child
    #   to allow host streams traits to be inherited
    if not stream.isatty():
        return None

    try:
        import fcntl
        import pty
        import struct
        import termios
    except ImportError:  # pragma: no cover
        return None  # cannot proceed on platforms without pty support

    try:
        main, child = pty.openpty()
    except OSError:  # could not open a tty
        return None  # pragma: no cover

    try:
        mode = termios.tcgetattr(stream)
        termios.tcsetattr(child, termios.TCSANOW, mode)
    except (termios.error, OSError):  # could not inherit traits
        return None  # pragma: no cover

    # adjust sub-process terminal size
    columns, lines = shutil.get_terminal_size(fallback=(-1, -1))
    if columns != -1 and lines != -1:
        size = struct.pack("HHHH", lines, columns, 0, 0)
        fcntl.ioctl(child, termios.TIOCSWINSZ, size)

    return main, child


__all__ = (
    "SIG_INTERRUPT",
    "CREATION_FLAGS",
    "LocalSubProcessExecuteInstance",
    "LocalSubProcessExecutor",
    "LocalSubprocessExecuteStatus",
    "LocalSubprocessExecuteFailedStatus",
)
