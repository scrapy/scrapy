"""
pprint and pformat wrappers with colorization support
"""

from __future__ import print_function
import sys
from pprint import pformat as pformat_

def _colorize(text, colorize=True):
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
