"""
This module provides functions added in Python 2.7, which weren't yet available
in Python 2.6. The Python 2.7 function is used when available.
"""

__all__ = ['OrderedDict']

try:
    from collections import OrderedDict
except ImportError:
    from scrapy.xlib.ordereddict import OrderedDict
