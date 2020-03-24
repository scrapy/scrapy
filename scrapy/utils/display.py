"""
pprint and pformat wrappers with colorization support
"""

import sys
import platform
from pprint import pformat as pformat_


def _colorize(text, colorize=True):


    if not colorize or not sys.stdout.isatty():
        return text
    try:
        if sys.platform == "win32" and platform.release() == "10":
            if platform.version() >= "10.0.14393":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

        colors = color_support_info()
        style = 'default'

        if colors == 256:
            format_options = {'style': style}
        elif style in ('light', 'dark'):
            format_options = {'bg': style}
        else:
            format_options = {'bg': 'dark'}
        
        from pygments.formatters import get_formatter_by_name
        import pygments.util
        
        format_alias = 'terminal256' if colors == 256 else 'terminal'
        
        try:
            formatter = get_formatter_by_name(format_alias, **format_options)
        except pygments.util.ClassNotFound as err:
            if self.debug:
                sys.stderr.write(str(err) + "\n")
            formatter = get_formatter_by_name(format_alias)
        
        from pygments import highlight
        from pygments.formatters import TerminalFormatter
        from pygments.lexers import PythonLexer
        return highlight(text, PythonLexer(), formatter)
    
    except ImportError:
        return text


def pformat(obj, *args, **kwargs):
    return _colorize(pformat_(obj), kwargs.pop('colorize', True))


def pprint(obj, *args, **kwargs):
    print(pformat(obj, *args, **kwargs))

def color_support_info():
    try:
        import curses
    except ImportError:
        # Usually Windows, which doesn't have great curses support
        return 16
    curses.setupterm()
    return curses.tigetnum('colors')