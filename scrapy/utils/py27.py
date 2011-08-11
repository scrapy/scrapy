"""
Similar to scrapy.utils.py26, but for Python 2.7
"""

__all__ = ['OrderedDict']

try:
    from collections import OrderedDict
except ImportError:
    from scrapy.xlib.ordereddict import OrderedDict
