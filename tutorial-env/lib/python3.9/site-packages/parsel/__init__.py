"""
Parsel lets you extract text from XML/HTML documents using XPath
or CSS selectors
"""

__author__ = "Scrapy project"
__email__ = "info@scrapy.org"
__version__ = "1.8.1"
__all__ = [
    "Selector",
    "SelectorList",
    "css2xpath",
    "xpathfuncs",
]

from parsel.selector import Selector, SelectorList  # NOQA
from parsel.csstranslator import css2xpath  # NOQA
from parsel import xpathfuncs  # NOQA

xpathfuncs.setup()
