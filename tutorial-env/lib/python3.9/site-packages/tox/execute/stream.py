from __future__ import annotations

from contextlib import contextmanager
from threading import Event, Lock, Timer
from typing import IO, TYPE_CHECKING, Iterator

from colorama import Fore

if TYPE_CHECKING:
    import sys
    from types import TracebackType

    if sys.version_info >= (3, 11):  # pragma: no cover (py311+)
        from typing import Self
    else:  # pragma: no cover (<py311)
        from typing_extensions import Self


class SyncWrite:
    """
    Make sure data collected is synced in-memory and to the target stream on every newline and time period.

    Used to propagate executed commands output to the standard output/error streams visible to the user.
    """

    REFRESH_RATE = 0.1

    def __init__(self, name: str, target: IO[bytes] | None, color: str | None = None) -> None:
        self._content = bytearray()
        self._target: IO[bytes] | None = target
        self._target_enabled: bool = target is not None
        self._keep_printing: Event = Event()
        self._content_lock: Lock = Lock()
        self._lock: Lock = Lock()
        self._at: int = 0
        self._color: str | None = color
        self.name = name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, target={self._target!r}, color={self._color!r})"

    def __enter__(self) -> Self:
        if self._target_enabled:
            self._start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._target_enabled:
            self._cancel()
            self._write(len(self._content))

    def handler(self, content: bytes) -> None:
        """A callback called whenever content is written."""
        with self._content_lock:
            self._content.extend(content)
            if self._target_enabled is False:
                return
            at = content.rfind(b"\n")
            if at != -1:  # pragma: no branch
                at = len(self._content) - len(content) + at + 1
        self._cancel()
        try:
            if at != -1:
                self._write(at)
        finally:
            self._start()

    def _start(self) -> None:
        self.timer = Timer(self.REFRESH_RATE, self._trigger_timer)
        self.timer.name = f"{self.name}-sync-timer"
        self.timer.start()

    def _cancel(self) -> None:
        self.timer.cancel()

    def _trigger_timer(self) -> None:
        with self._content_lock:
            at = len(self._content)
        self._write(at)

    def _write(self, at: int) -> None:
        assert self._target is not None  # because _do_print is guarding the call of this method  # noqa: S101
        with self._lock:
            if at > self._at:  # pragma: no branch
                try:
                    with self.colored():
                        self._target.write(self._content[self._at : at])
                    self._target.flush()
                finally:
                    self._at = at

    @contextmanager
    def colored(self) -> Iterator[None]:
        if self._color is None or self._target is None:
            yield
        else:
            self._target.write(self._color.encode("utf-8"))
            try:
                yield
            finally:
                self._target.write(Fore.RESET.encode("utf-8"))

    @property
    def text(self) -> str:
        with self._content_lock:
            return self._content.decode("utf-8", errors="surrogateescape")

    @property
    def content(self) -> bytearray:
        with self._content_lock:
            return self._content
