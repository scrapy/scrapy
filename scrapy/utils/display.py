"""
Helper functions for formatting and pretty printing some objects
"""
import sys
import pprint as pypprint

from scrapy.item import BaseItem
from scrapy.http import Request, Response

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

def pformat_dictobj(obj):
    clsname = obj.__class__.__name__
    return "%s(%s)\n" % (clsname, colorize(pypprint.pformat(obj.__dict__)))

def pprint_dictobj(obj):
    print pformat_dictobj(obj)

def pformat(obj, *args, **kwargs):
    """
    Wrapper which autodetects the object type and uses the proper formatting
    function
    """

    if isinstance(obj, (list, tuple)):
        return "".join([pformat(i, *args, **kwargs) for i in obj])
    elif isinstance(obj, (BaseItem, Request, Response)):
        return pformat_dictobj(obj)
    else:
        return colorize(pypprint.pformat(obj))

def pprint(obj, *args, **kwargs):
    """
    Wrapper which autodetects the object type and uses the proper printing
    function
    """

    print pformat(obj, *args, **kwargs)
