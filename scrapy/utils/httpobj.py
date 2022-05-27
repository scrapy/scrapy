"""Helper functions for scrapy.http objects (Request, Response)"""

from typing import Union
from urllib.parse import urlparse, ParseResult
from weakref import WeakKeyDictionary

import scrapy


_urlparse_cache: "WeakKeyDictionary[Union[scrapy.Request, scrapy.http.response.Response], ParseResult]"
_urlparse_cache = WeakKeyDictionary()


def urlparse_cached(request_or_response: Union["scrapy.Request", "scrapy.http.response.Response"]) -> ParseResult:
    """Return urlparse.urlparse caching the result, where the argument can be a Request or Response object"""
    if request_or_response not in _urlparse_cache:
        _urlparse_cache[request_or_response] = urlparse(request_or_response.url)
    return _urlparse_cache[request_or_response]
