"""
pprint and pformat wrappers with colorization support
"""

import ctypes
import platform
import sys
from pprint import pformat as pformat_
from typing import Any

from packaging.version import Version as parse_version


def _enable_windows_terminal_processing() -> bool:
    # https://stackoverflow.com/a/36760881
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))


def _tty_supports_color() -> bool:
    if sys.platform != "win32":
        return True

    if parse_version(platform.version()) < parse_version("10.0.14393"):
        return True

    # Windows >= 10.0.14393 interprets ANSI escape sequences providing terminal
    # processing is enabled.
    return _enable_windows_terminal_processing()


def _colorize(text: str, colorize: bool = True) -> str:
    if not colorize or not sys.stdout.isatty() or not _tty_supports_color():
        return text
    try:
        from pygments import highlight
    except ImportError:
        return text
    else:
        from pygments.formatters import TerminalFormatter
        from pygments.lexers import PythonLexer

        return highlight(text, PythonLexer(), TerminalFormatter())


def pformat(obj: Any, *args: Any, **kwargs: Any) -> str:
    return _colorize(pformat_(obj), kwargs.pop("colorize", True))


def pprint(obj: Any, *args: Any, **kwargs: Any) -> None:
    print(pformat(obj, *args, **kwargs))
