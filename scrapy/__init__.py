"""
Scrapy - a web crawling and web scraping framework written for Python
"""

__all__ = ['__version__', 'version_info', 'twisted_version',
           'Spider', 'Request', 'FormRequest', 'Selector', 'Item', 'Field']

# Scrapy version
import pkgutil
__version__ = pkgutil.get_data(__package__, 'VERSION').decode('ascii').strip()
version_info = tuple(int(v) if v.isdigit() else v
                     for v in __version__.split('.'))
del pkgutil

# Check minimum required Python version
import sys
if sys.version_info < (3, 5):
    print("Scrapy %s requires Python 3.5" % __version__)
    sys.exit(1)

# Ignore noisy twisted deprecation warnings
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning, module='twisted')
del warnings

# Install twisted asyncio loop
def _install_asyncio_reactor():
    global asyncio_supported
    try:
        import asyncio
        from twisted.internet import asyncioreactor
    except ImportError:
        pass
    else:
        from twisted.internet.error import ReactorAlreadyInstalledError
        try:
            asyncioreactor.install(asyncio.get_event_loop())
            asyncio_supported = True
        except ReactorAlreadyInstalledError:
            import twisted.internet.reactor
            if isinstance(twisted.internet.reactor,
                              asyncioreactor.AsyncioSelectorReactor):
                asyncio_supported = True
asyncio_supported = False
_install_asyncio_reactor()
del _install_asyncio_reactor

# Apply monkey patches to fix issues in external libraries
from . import _monkeypatches
del _monkeypatches

from twisted import version as _txv
twisted_version = (_txv.major, _txv.minor, _txv.micro)

# Declare top-level shortcuts
from scrapy.spiders import Spider
from scrapy.http import Request, FormRequest
from scrapy.selector import Selector
from scrapy.item import Item, Field

del sys
