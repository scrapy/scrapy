"""
Scrapy - a web crawling and web scraping framework written for Python
"""

import sys
import warnings
from importlib.resources import files

# Declare top-level shortcuts
from scrapy.http import FormRequest, Request
from scrapy.item import Field, Item
from scrapy.selector import Selector
from scrapy.spiders import Spider

__all__ = [
    "Field",
    "FormRequest",
    "Item",
    "Request",
    "Selector",
    "Spider",
    "__version__",
    "version_info",
]


# Scrapy and Twisted versions
__version__ = files("scrapy").joinpath("VERSION").read_text(encoding="ascii").strip()
version_info = tuple(int(v) if v.isdigit() else v for v in __version__.split("."))


# Ignore noisy twisted deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="twisted")


del files
del sys
del warnings
