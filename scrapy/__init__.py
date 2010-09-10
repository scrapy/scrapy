"""
Scrapy - a screen scraping framework written in Python
"""

version_info = (0, 10, 0, '')
__version__ = "0.10"

import sys, os, warnings

if sys.version_info < (2,5):
    print "Scrapy %s requires Python 2.5 or above" % __version__
    sys.exit(1)

# ignore noisy twisted deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning, module='twisted')

# prevents noisy (and innocent) dropin.cache errors when loading spiders from
# egg files using the old Spider Manager. TODO: Remove for Scrapy 0.11
from twisted.python.zippath import ZipPath
ZipPath.setContent = lambda x, y: None

# monkey patches to fix external library issues
from scrapy.xlib import twisted_250_monkeypatches, urlparse_monkeypatches

# optional_features is a set containing Scrapy optional features
optional_features = set()

try:
    import OpenSSL
except ImportError:
    pass
else:
    optional_features.add('ssl')

try:
    import boto
except ImportError:
    pass
else:
    optional_features.add('boto')
