# FIXME: code below is for backwards compatibility and should be removed before
# the 0.7 release

import warnings

from scrapy.contrib.downloadermiddleware.httpcache import HttpCacheMiddleware

class CacheMiddleware(HttpCacheMiddleware):

    def __init__(self, *args, **kwargs):
        warnings.warn("scrapy.contrib.downloadermiddleware.cache.CacheMiddleware was moved to scrapy.contrib.downloadermiddleware.httpcache.HttpCacheMiddleware",
            DeprecationWarning, stacklevel=2)
        HttpCacheMiddleware.__init__(self, *args, **kwargs)

