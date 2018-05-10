"""Helper functions for scrapy.http objects (Request, Response)"""

import weakref

from six.moves.urllib.parse import urlparse

_urlparse_cache = weakref.WeakKeyDictionary()
def urlparse_cached(request_or_response):
    """Return urlparse.urlparse caching the result, where the argument can be a
    Request or Response object
    """
    if request_or_response not in _urlparse_cache:
        #Make sure we clean out any domains that might have \n, \t in them.
        url = request_or_response.url.strip()
        _urlparse_cache[request_or_response] = urlparse(url)
    return _urlparse_cache[request_or_response]
