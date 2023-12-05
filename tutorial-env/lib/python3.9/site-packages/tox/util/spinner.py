"""A minimal non-colored version of https://pypi.org/project/halo, to track list progress."""
from __future__ import annotations

import os
import sys
import textwrap
import threading
import time
from collections import OrderedDict
from typing import IO, TYPE_CHECKING, NamedTuple, Sequence, TypeVar

from colorama import Fore

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Any, ClassVar

if sys.platform == "win32":  # pragma: win32 cover
    import ctypes

    class _CursorInfo(ctypes.Structure):
        _fields_: ClassVar[list[tuple[str, Any]]] = [("size", ctypes.c_int), ("visible", ctypes.c_byte)]


def _file_support_encoding(chars: Sequence[str], file: IO[str]) -> bool:
    encoding = getattr(file, "encoding", None)
    if encoding is not None:  # pragma: no branch  # this should be always set, unless someone passes in something bad
        try:
            for char in chars:
                char.encode(encoding)
        except UnicodeEncodeError:
            pass
        else:
            return True
    return False


T = TypeVar("T", bound="Spinner")
MISS_DURATION = 0.01


class Outcome(NamedTuple):
    ok: str
    fail: str
    skip: str


class Spinner:
    CLEAR_LINE = "\033[K"
    max_width = 120
    UNICODE_FRAMES: ClassVar[list[str]] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    ASCII_FRAMES: ClassVar[list[str]] = ["|", "-", "+", "x", "*"]
    UNICODE_OUTCOME = Outcome(ok="✔", fail="✖", skip="⚠")
    ASCII_OUTCOME = Outcome(ok="+", fail="!", skip="?")

    def __init__(  # noqa: PLR0913
        self,
        enabled: bool = True,  # noqa: FBT001, FBT002
        refresh_rate: float = 0.1,
        colored: bool = True,  # noqa: FBT001, FBT002
        stream: IO[str] | None = None,
        total: int | None = None,
    ) -> None:
        self.is_colored = colored
        self.refresh_rate = refresh_rate
        self.enabled = enabled
        stream = sys.stdout if stream is None else stream
        self.frames = self.UNICODE_FRAMES if _file_support_encoding(self.UNICODE_FRAMES, stream) else self.ASCII_FRAMES
        self.outcome = (
            self.UNICODE_OUTCOME if _file_support_encoding(self.UNICODE_OUTCOME, stream) else self.ASCII_OUTCOME
        )
        self.stream = stream
        self.total = total
        self.print_report = True

        self._envs: dict[str, float] = OrderedDict()
        self._frame_index = 0

    def clear(self) -> None:
        if self.enabled:
            self.stream.write("\r")
            self.stream.write(self.CLEAR_LINE)

    def render(self) -> Spinner:
        while True:
            self._stop_spinner.wait(self.refresh_rate)
            if self._stop_spinner.is_set():
                break
            self.render_frame()
        return self

    def render_frame(self) -> None:
        if self.enabled:
            self.clear()
            self.stream.write(f"\r{self.frame()}")

    def frame(self) -> str:
        frame = self.frames[self._frame_index]
        self._frame_index += 1
        self._frame_index %= len(self.frames)
        total = f"/{self.total}" if self.total is not None else ""
        text_frame = f"[{len(self._envs)}{total}] {' | '.join(self._envs)}"
        text_frame = textwrap.shorten(text_frame, width=self.max_width - 1, placeholder="...")
        return f"{frame} {text_frame}"

    def __enter__(self: T) -> T:
        if self.enabled:
            self.disable_cursor()
        self.render_frame()
        self._stop_spinner = threading.Event()
        self._spinner_thread = threading.Thread(target=self.render)
        self._spinner_thread.daemon = True
        self._spinner_thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if not self._stop_spinner.is_set():  # pragma: no branch
            if self._spinner_thread:  # pragma: no branch # hard to test
                self._stop_spinner.set()
                self._spinner_thread.join()

            self._frame_index = 0
            if self.enabled:
                self.clear()
                self.enable_cursor()

    def add(self, name: str) -> None:
        self._envs[name] = time.monotonic()

    def succeed(self, key: str) -> None:
        self.finalize(key, f"OK {self.outcome.ok}", Fore.GREEN)

    def fail(self, key: str) -> None:
        self.finalize(key, f"FAIL {self.outcome.fail}", Fore.RED)

    def skip(self, key: str) -> None:
        self.finalize(key, f"SKIP {self.outcome.skip}", Fore.YELLOW)

    def finalize(self, key: str, status: str, color: str) -> None:
        start_at = self._envs.pop(key, None)
        if self.enabled:
            self.clear()
        if self.print_report:
            duration = MISS_DURATION if start_at is None else time.monotonic() - start_at
            base = f"{key}: {status} in {td_human_readable(duration)}"
            if self.is_colored:
                base = f"{color}{base}{Fore.RESET}"
            base += os.linesep
            self.stream.write(base)

    def disable_cursor(self) -> None:
        if self.stream.isatty():
            if sys.platform == "win32":  # pragma: win32 cover
                ci = _CursorInfo()
                handle = ctypes.windll.kernel32.GetStdHandle(-11)
                ctypes.windll.kernel32.GetConsoleCursorInfo(handle, ctypes.byref(ci))
                ci.visible = False
                ctypes.windll.kernel32.SetConsoleCursorInfo(handle, ctypes.byref(ci))
            else:
                self.stream.write("\033[?25l")

    def enable_cursor(self) -> None:
        if self.stream.isatty():
            if sys.platform == "win32":  # pragma: win32 cover
                ci = _CursorInfo()
                handle = ctypes.windll.kernel32.GetStdHandle(-11)
                ctypes.windll.kernel32.GetConsoleCursorInfo(handle, ctypes.byref(ci))
                ci.visible = True
                ctypes.windll.kernel32.SetConsoleCursorInfo(handle, ctypes.byref(ci))
            else:
                self.stream.write("\033[?25h")


_PERIODS = [
    ("day", 60 * 60 * 24),
    ("hour", 60 * 60),
    ("minute", 60),
    ("second", 1),
]


def td_human_readable(seconds: float) -> str:
    texts: list[str] = []
    for period_name, period_seconds in _PERIODS:
        period_str = None
        if period_name == "second" and (seconds >= 0.01 or not texts):  # noqa: PLR2004
            period_str = f"{seconds:.2f}".rstrip("0").rstrip(".")
        elif seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            period_str = f"{period_value:.0f}"
        if period_str is not None:
            texts.append(f"{period_str} {period_name}{'' if period_str == '1' else 's'}")
    return " ".join(texts)
