"""
Scrapy - a screen scraping framework written in Python
"""

version_info = (0, 9, 0, 'dev')
__version__ = "0.9-dev"

import sys, os

if sys.version_info < (2,5):
    print "Scrapy %s requires Python 2.5 or above" % __version__
    sys.exit(1)

# monkey patches to fix external library issues
from scrapy.xlib import twisted_250_monkeypatches

# optional_features is a set containing Scrapy optional features
optional_features = set()

try:
    import OpenSSL
except ImportError:
    pass
else:
    optional_features.add('ssl')
