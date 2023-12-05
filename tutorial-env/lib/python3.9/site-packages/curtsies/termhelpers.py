import tty
import termios
import fcntl
import os

from typing import IO, ContextManager, Type, List, Union, Optional
from types import TracebackType

_Attr = List[Union[int, List[Union[bytes, int]]]]


class Nonblocking(ContextManager):
    """
    A context manager for making an input stream nonblocking.
    """

    def __init__(self, stream: IO) -> None:
        self.stream = stream
        self.fd = self.stream.fileno()

    def __enter__(self) -> None:
        self.orig_fl = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, self.orig_fl | os.O_NONBLOCK)

    def __exit__(
        self,
        type: Optional[Type[BaseException]] = None,
        value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        fcntl.fcntl(self.fd, fcntl.F_SETFL, self.orig_fl)


class Termmode(ContextManager):
    def __init__(self, stream: IO, attrs: _Attr) -> None:
        self.stream = stream
        self.attrs = attrs

    def __enter__(self) -> None:
        self.original_stty = termios.tcgetattr(self.stream)
        termios.tcsetattr(self.stream, termios.TCSANOW, self.attrs)

    def __exit__(
        self,
        type: Optional[Type[BaseException]] = None,
        value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        termios.tcsetattr(self.stream, termios.TCSANOW, self.original_stty)


class Cbreak(ContextManager[Termmode]):
    def __init__(self, stream: IO) -> None:
        self.stream = stream

    def __enter__(self) -> Termmode:
        self.original_stty = termios.tcgetattr(self.stream)
        tty.setcbreak(self.stream, termios.TCSANOW)
        return Termmode(self.stream, self.original_stty)

    def __exit__(
        self,
        type: Optional[Type[BaseException]] = None,
        value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        termios.tcsetattr(self.stream, termios.TCSANOW, self.original_stty)
