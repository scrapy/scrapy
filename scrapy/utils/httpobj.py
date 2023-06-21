"""Helper functions for scrapy.http objects (Request, Response)"""

from typing import Union
from urllib.parse import ParseResult, urlparse
from weakref import WeakKeyDictionary

from scrapy.http import Request, Response

_urlparse_cache: "WeakKeyDictionary[Union[Request, Response], ParseResult]" = (
    WeakKeyDictionary()
)


def urlparse_cached(request_or_response: Union[Request, Response]) -> ParseResult:
    """Return urlparse.urlparse caching the result, where the argument can be a
    Request or Response object
    """
    if request_or_response not in _urlparse_cache:
        _urlparse_cache[request_or_response] = urlparse(request_or_response.url)
    return _urlparse_cache[request_or_response]
