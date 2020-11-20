"""
Scrapy - a web crawling and web scraping framework written for Python
"""

import pkgutil
import sys
import warnings

from twisted import version as _txv

# Declare top-level shortcuts
from scrapy.spiders import Spider
from scrapy.http import Request, FormRequest
from scrapy.selector import Selector
from scrapy.item import Item, Field


__all__ = [
    '__version__', 'version_info', 'twisted_version', 'Spider',
    'Request', 'FormRequest', 'Selector', 'Item', 'Field',
]


# Scrapy and Twisted versions
__version__ = pkgutil.get_data(__package__, 'VERSION').decode('ascii').strip()
version_info = tuple(int(v) if v.isdigit() else v for v in __version__.split('.'))
twisted_version = (_txv.major, _txv.minor, _txv.micro)


# Check minimum required Python version
if sys.version_info < (3, 6):
    print("Scrapy %s requires Python 3.6+" % __version__)
    sys.exit(1)


# Ignore noisy twisted deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning, module='twisted')


del pkgutil
del sys
del warnings
