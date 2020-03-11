"""
pprint and pformat wrappers with colorization support
"""

import sys
import platform
from pprint import pformat as pformat_


def _colorize(text, colorize=True):
    if sys.platform == "win32" and platform.release() == "10" and platform.version() >= "10.0.14393":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    if not colorize or not sys.stdout.isatty():
        return text
    try:
        from pygments import highlight
        from pygments.formatters import TerminalFormatter
        from pygments.lexers import PythonLexer
        return highlight(text, PythonLexer(), TerminalFormatter())
    except ImportError:
        return text


def pformat(obj, *args, **kwargs):
    return _colorize(pformat_(obj), kwargs.pop('colorize', True))


def pprint(obj, *args, **kwargs):
    print(pformat(obj, *args, **kwargs))
