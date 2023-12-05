"""A reader that drain a stream via its file no on a background thread."""
from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Event, Thread
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import sys
    from types import TracebackType

    if sys.version_info >= (3, 11):  # pragma: no cover (py311+)
        from typing import Self
    else:  # pragma: no cover (<py311)
        from typing_extensions import Self


WAIT_GENERAL = 0.05  # stop thread join every so often (give chance to a signal interrupt)


class ReadViaThread(ABC):
    def __init__(self, file_no: int, handler: Callable[[bytes], None], name: str, drain: bool) -> None:  # noqa: FBT001
        self.file_no = file_no
        self.stop = Event()
        self.thread = Thread(target=self._read_stream, name=f"tox-r-{name}-{file_no}")
        self.handler = handler
        self._on_exit_drain = drain

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop.set()  # signal thread to stop
        while self.thread.is_alive():  # wait until it stops
            self.thread.join(WAIT_GENERAL)
        self._drain_stream()  # read anything left

    @abstractmethod
    def _read_stream(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _drain_stream(self) -> None:
        raise NotImplementedError
