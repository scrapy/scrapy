"""Helper functions for scrapy.http objects (Request, Response)"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    from scrapy.http import Request, Response


_urlparse_cache: WeakKeyDictionary[Request | Response, ParseResult] = (
    WeakKeyDictionary()
)


def urlparse_cached(request_or_response: Request | Response) -> ParseResult:
    """Return urlparse.urlparse caching the result, where the argument can be a
    Request or Response object
    """
    if request_or_response not in _urlparse_cache:
        _urlparse_cache[request_or_response] = urlparse(request_or_response.url)
    return _urlparse_cache[request_or_response]
