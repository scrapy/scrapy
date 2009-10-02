"""
Helper functions for formatting and pretty printing some objects
"""
import sys
import pprint as pypprint

from scrapy.item import BaseItem

nocolour = False

def colorize(text):
    if nocolour or not sys.stdout.isatty():
        return text
    try:
        from pygments import highlight
        from pygments.formatters import TerminalFormatter
        from pygments.lexers import PythonLexer
        return highlight(text, PythonLexer(), TerminalFormatter())
    except ImportError:
        return text

def _pformat_dictobj(obj):
    clsname = obj.__class__.__name__
    return "%s(%s)\n" % (clsname, colorize(pypprint.pformat(obj.__dict__)))

def pformat(obj, *args, **kwargs):
    """
    Wrapper which autodetects the object type and uses the proper formatting
    function
    """
    if isinstance(obj, BaseItem):
        return _pformat_dictobj(obj)
    elif hasattr(obj, '__iter__'):
        return "".join(map(pformat, obj))
    else:
        return colorize(pypprint.pformat(repr(obj)))

def pprint(obj, *args, **kwargs):
    """
    Wrapper which autodetects the object type and uses the proper printing
    function
    """
    print pformat(obj, *args, **kwargs)
