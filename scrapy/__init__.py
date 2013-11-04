"""
Scrapy - a screen scraping framework written in Python
"""
from __future__ import print_function
import pkgutil
__version__ = pkgutil.get_data(__package__, 'VERSION').strip()
if not isinstance(__version__, str):
    __version__ = __version__.decode('ascii')
version_info = tuple(__version__.split('.')[:3])

import sys, os, warnings

if sys.version_info < (2, 7):
    print("Scrapy %s requires Python 2.7" % __version__)
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
    import django
except ImportError:
    pass
else:
    optional_features.add('django')

from twisted import version as _txv
twisted_version = (_txv.major, _txv.minor, _txv.micro)
if twisted_version >= (11, 1, 0):
    optional_features.add('http11')
