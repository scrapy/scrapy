"""Helper functions for scrapy.http objects (Request, Response)"""

import weakref


####
#   The changes to the following block is targeted at making scrapy available
#   in both Python 2.7 and Python 3.x . The original code is commented out.

#from urlparse import urlparse

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

####


_urlparse_cache = weakref.WeakKeyDictionary()
def urlparse_cached(request_or_response):
    """Return urlparse.urlparse caching the result, where the argument can be a
    Request or Response object
    """
    if request_or_response not in _urlparse_cache:
        _urlparse_cache[request_or_response] = urlparse(request_or_response.url)
    return _urlparse_cache[request_or_response]
