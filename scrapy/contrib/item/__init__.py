"""
WARNING: This module is obsolete and will be removed before the Scrapy 0.7
release
"""

import warnings

from scrapy.contrib.item.models import RobustScrapedItem, RobustItemDelta, ValidationError, ValidationPipeline

warnings.warn("scrapy.contrib.item is obsolete and will be removed soon", \
                DeprecationWarning, stacklevel=2)
