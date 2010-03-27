"""
Scrapy - a screen scraping framework written in Python
"""

version_info = (0, 8, 0, '', 0)
__version__ = "0.8"

import sys, os, warnings

if sys.version_info < (2,5):
    print "Scrapy %s requires Python 2.5 or above" % __version__
    sys.exit(1)

# ignore noisy twisted deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning, module='twisted')

# monkey patches to fix external library issues
from scrapy.xlib import twisted_250_monkeypatches

# add some common encoding aliases not included by default in Python
from scrapy.utils.encoding import add_encoding_alias
add_encoding_alias('gb2312', 'zh-cn')
add_encoding_alias('cp1251', 'win-1251')

# optional_features is a set containing Scrapy optional features
optional_features = set()

try:
    import OpenSSL
except ImportError:
    pass
else:
    optional_features.add('ssl')
