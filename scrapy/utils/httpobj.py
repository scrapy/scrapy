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
    """Return the result of parsing the URL of *request_or_response*, a
    :class:`~scrapy.Request` or :class:`~scrapy.http.Response` object, with
    :func:`urllib.parse.urlparse`.

    The result is cached, using a :class:`weakref.WeakKeyDictionary` keyed on
    *request_or_response*, so that the URL of a given object is parsed only
    once. Prefer this function over calling :func:`urllib.parse.urlparse` on
    ``request_or_response.url`` directly when the same URL may be parsed more
    than once.
    """
    if request_or_response not in _urlparse_cache:
        _urlparse_cache[request_or_response] = urlparse(request_or_response.url)
    return _urlparse_cache[request_or_response]
