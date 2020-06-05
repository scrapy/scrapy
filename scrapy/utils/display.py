"""
pprint and pformat wrappers with colorization support
"""

import sys
from distutils.version import LooseVersion as parse_version
from platform import version
from pprint import pformat as pformat_


def _colorize(text, colorize=True):
    if not colorize or not sys.stdout.isatty():
        return text
    try:
        from pygments.formatters import TerminalFormatter
        from pygments import highlight
        from pygments.lexers import PythonLexer
    except ImportError:
        return text

    # All Windows versions >= "10.0.14393" interpret ANSI escape sequences
    # using terminal processing.
    #
    # Enable enivornment variable `ENABLE_VIRTUAL_TERMINAL_PROCESSING`
    # to activate terminal processing.
    if sys.platform == "win32" and parse_version(version()) >= parse_version("10.0.14393"):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            # set `ENABLE_VIRTUAL_TERMINAL_PROCESSING` flag
            if not kernel32.SetConsoleMode(handle, 7):
                raise ValueError
        except ValueError:
            return text

    if _color_support_info():
        return highlight(text, PythonLexer(), TerminalFormatter())

    return text


def _color_support_info():
    try:
        import curses
    except ImportError:
        # Usually Windows, which doesn't have great curses support
        return True

    try:
        curses.initscr()
        color_support = curses.has_colors()
        curses.endwin()
        return color_support
    except curses.error:
        pass

    return False


def pformat(obj, *args, **kwargs):
    return _colorize(pformat_(obj), kwargs.pop('colorize', True))


def pprint(obj, *args, **kwargs):
    print(pformat(obj, *args, **kwargs))
