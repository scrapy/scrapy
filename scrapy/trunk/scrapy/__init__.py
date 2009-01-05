"""
Scrapy - a screen scraping framework written in Python
"""

__version__ = "0.7.0"

import sys, os

if sys.version_info < (2,5):
    print "Scrapy %s requires Python 2.5 or above" % __version__
    sys.exit(1)

# add external python libraries bundled into scrapy
sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), "xlib"))

# monkey patches to fix external library issues
from scrapy.patches import monkeypatches
monkeypatches.apply_patches()
