"""Helper functions for scrapy.http objects (Request, Response)"""

import weakref
from urllib.parse import urlparse


_urlparse_cache = weakref.WeakKeyDictionary()


def urlparse_cached(request_or_response):
    """Return urlparse.urlparse caching the result, where the argument can be a
    Request or Response object
    """
    if request_or_response not in _urlparse_cache:
        _urlparse_cache[request_or_response] = urlparse(request_or_response.url)
    return _urlparse_cache[request_or_response]
