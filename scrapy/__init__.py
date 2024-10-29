"""
Scrapy - a web crawling and web scraping framework written for Python
"""

import pkgutil
import sys
import warnings

# Declare top-level shortcuts
from scrapy.http import FormRequest, Request
from scrapy.item import Field, Item
from scrapy.selector import Selector
from scrapy.spiders import Spider

__all__ = [
    "__version__",
    "version_info",
    "Spider",
    "Request",
    "FormRequest",
    "Selector",
    "Item",
    "Field",
]


# Scrapy and Twisted versions
__version__ = (pkgutil.get_data(__package__, "VERSION") or b"").decode("ascii").strip()
version_info = tuple(int(v) if v.isdigit() else v for v in __version__.split("."))


def __getattr__(name: str):
    if name == "twisted_version":
        import warnings

        from twisted import version as _txv

        from scrapy.exceptions import ScrapyDeprecationWarning

        warnings.warn(
            "The scrapy.twisted_version attribute is deprecated, use twisted.version instead",
            ScrapyDeprecationWarning,
        )
        return _txv.major, _txv.minor, _txv.micro

    raise AttributeError


# Ignore noisy twisted deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="twisted")


del pkgutil
del sys
del warnings
