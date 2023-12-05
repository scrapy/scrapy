"""On UNIX we use select.select to ensure we drain in a non-blocking fashion."""
from __future__ import annotations

import errno  # pragma: win32 no cover
import os  # pragma: win32 no cover
import select  # pragma: win32 no cover
from typing import Callable

from .read_via_thread import ReadViaThread  # pragma: win32 no cover

STOP_EVENT_CHECK_PERIODICITY_IN_MS = 0.01  # pragma: win32 no cover


class ReadViaThreadUnix(ReadViaThread):  # pragma: win32 no cover
    def __init__(self, file_no: int, handler: Callable[[bytes], None], name: str, drain: bool) -> None:  # noqa: FBT001
        super().__init__(file_no, handler, name, drain)

    def _read_stream(self) -> None:
        while not self.stop.is_set():
            # we need to drain the stream, but periodically give chance for the thread to break if the stop event has
            # been set (this is so that an interrupt can be handled)
            if self._read_available() is None:  # pragma: no branch
                break  # pragma: no cover

    def _drain_stream(self) -> None:
        # no block just poll
        while True:
            if self._read_available(timeout=0) is not True:  # pragma: no branch
                break  # pragma: no cover

    def _read_available(self, timeout: float = STOP_EVENT_CHECK_PERIODICITY_IN_MS) -> bool | None:
        try:
            ready, __, ___ = select.select([self.file_no], [], [], timeout)
            if ready:
                data = os.read(self.file_no, 1024)  # read up to 1024 characters
                # If the end of the file referred to by fd has been reached, an empty bytes object is returned.
                if data:
                    self.handler(data)
                    return True
        except OSError as exception:  # pragma: no cover
            # Bad file descriptor or Input/output error
            if exception.errno in (errno.EBADF, errno.EIO):
                return None
            raise
        else:
            return False
