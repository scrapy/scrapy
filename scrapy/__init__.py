"""
Scrapy - a web crawling and web scraping framework written for Python
"""

__all__ = ['__version__', 'version_info', 'optional_features', 'twisted_version',
           'Spider', 'Request', 'FormRequest', 'Selector', 'Item', 'Field']

# Scrapy version
import pkgutil
__version__ = pkgutil.get_data(__package__, 'VERSION').decode('ascii').strip()
version_info = tuple(int(v) if v.isdigit() else v
                     for v in __version__.split('.'))
del pkgutil

# Check minimum required Python version
import sys
if sys.version_info < (2, 7):
    print("Scrapy %s requires Python 2.7" % __version__)
    sys.exit(1)

# Ignore noisy twisted deprecation warnings
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning, module='twisted')
del warnings

# Apply monkey patches to fix issues in external libraries
from . import _monkeypatches
del _monkeypatches

# WARNING: optional_features set is deprecated and will be removed soon. Do not use.
optional_features = set()
# TODO: backwards compatibility, remove for Scrapy 0.20
optional_features.add('ssl')
try:
    import boto
    del boto
except ImportError:
    pass
else:
    optional_features.add('boto')

from twisted import version as _txv
twisted_version = (_txv.major, _txv.minor, _txv.micro)
if twisted_version >= (11, 1, 0):
    optional_features.add('http11')

# Declare top-level shortcuts
from scrapy.spiders import Spider
from scrapy.http import Request, FormRequest
from scrapy.selector import Selector
from scrapy.item import Item, Field

del sys
