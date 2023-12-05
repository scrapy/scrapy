# The MIT License
#
# Copyright (c) 2015-2021 Sebastian Ramacher
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from typing import Optional, Type, IO
from ._typing_compat import Literal
from types import TracebackType

has_fcntl = True
try:
    import fcntl
    import errno
except ImportError:
    has_fcntl = False

has_msvcrt = True
try:
    import msvcrt
    import os
except ImportError:
    has_msvcrt = False


class BaseLock:
    """Base class for file locking"""

    def __init__(self) -> None:
        self.locked = False

    def acquire(self) -> None:
        pass

    def release(self) -> None:
        pass

    def __enter__(self) -> "BaseLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Literal[False]:
        if self.locked:
            self.release()
        return False

    def __del__(self) -> None:
        if self.locked:
            self.release()


class UnixFileLock(BaseLock):
    """Simple file locking for Unix using fcntl"""

    def __init__(self, fileobj, mode: int = 0) -> None:
        super().__init__()
        self.fileobj = fileobj
        self.mode = mode | fcntl.LOCK_EX

    def acquire(self) -> None:
        try:
            fcntl.flock(self.fileobj, self.mode)
            self.locked = True
        except OSError as e:
            if e.errno != errno.ENOLCK:
                raise e

    def release(self) -> None:
        self.locked = False
        fcntl.flock(self.fileobj, fcntl.LOCK_UN)


class WindowsFileLock(BaseLock):
    """Simple file locking for Windows using msvcrt"""

    def __init__(self, filename: str) -> None:
        super().__init__()
        self.filename = f"{filename}.lock"
        self.fileobj = -1

    def acquire(self) -> None:
        # create a lock file and lock it
        self.fileobj = os.open(
            self.filename, os.O_RDWR | os.O_CREAT | os.O_TRUNC
        )
        msvcrt.locking(self.fileobj, msvcrt.LK_NBLCK, 1)

        self.locked = True

    def release(self) -> None:
        self.locked = False

        # unlock lock file and remove it
        msvcrt.locking(self.fileobj, msvcrt.LK_UNLCK, 1)
        os.close(self.fileobj)
        self.fileobj = -1

        try:
            os.remove(self.filename)
        except OSError:
            pass


def FileLock(
    fileobj: IO, mode: int = 0, filename: Optional[str] = None
) -> BaseLock:
    if has_fcntl:
        return UnixFileLock(fileobj, mode)
    elif has_msvcrt and filename is not None:
        return WindowsFileLock(filename)
    return BaseLock()


# vim: sw=4 ts=4 sts=4 ai et
