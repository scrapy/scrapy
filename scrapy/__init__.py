"""
Scrapy - a web crawling and web scraping framework written for Python
"""

__all__ = ['__version__', 'version_info', 'twisted_version',
           'Spider', 'Request', 'FormRequest', 'Selector', 'Item', 'Field']

# Scrapy version
import pkgutil  # isort:skip
__version__ = pkgutil.get_data(__package__, 'VERSION').decode('ascii').strip()
version_info = tuple(int(v) if v.isdigit() else v
                     for v in __version__.split('.'))
del pkgutil

# Check minimum required Python version
import sys  # isort:skip
if sys.version_info < (2, 7):
    print("Scrapy %s requires Python 2.7" % __version__)
    sys.exit(1)

# Ignore noisy twisted deprecation warnings
import warnings  # isort:skip
warnings.filterwarnings('ignore', category=DeprecationWarning, module='twisted')
del warnings

# Apply monkey patches to fix issues in external libraries
from . import _monkeypatches  # isort:skip
del _monkeypatches

from twisted import version as _txv  # isort:skip
twisted_version = (_txv.major, _txv.minor, _txv.micro)

# Declare top-level shortcuts
from scrapy.http import FormRequest, Request
from scrapy.item import Field, Item
from scrapy.selector import Selector
from scrapy.spiders import Spider

del sys
