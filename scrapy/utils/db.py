import warnings

from scrapy.utils.mysql import *

warnings.warn("scrapy.utils.db module is depreacted, use scrapy.utils.mysql instead",
    DeprecationWarning, stacklevel=2)
