"""
Scrapy - a screen scraping framework written in Python
"""
import pkgutil
__version__ = pkgutil.get_data(__package__, 'VERSION').strip()
version_info = tuple(__version__.split('.')[:3])

import sys, os, warnings

if sys.version_info < (2,6):
    print "Scrapy %s requires Python 2.6 or above" % __version__
    sys.exit(1)

# ignore noisy twisted deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning, module='twisted')

# monkey patches to fix external library issues
from scrapy.xlib import urlparse_monkeypatches

# WARNING: optional_features set is deprecated and will be removed soon. Do not use.
optional_features = set()

# TODO: backwards compatibility, remove for Scrapy 0.20
optional_features.add('ssl')

try:
    import boto
except ImportError:
    pass
else:
    optional_features.add('boto')

try:
    import libxml2
except ImportError:
    pass
else:
    optional_features.add('libxml2')

try:
    import django
except ImportError:
    pass
else:
    optional_features.add('django')
