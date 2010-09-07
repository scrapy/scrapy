from scrapy.signals import *

import warnings
warnings.warn("scrapy.core.signals is deprecated and will be removed in Scrapy 0.11, use scrapy.signals instead", \
    DeprecationWarning, stacklevel=2)

request_uploaded = response_downloaded
