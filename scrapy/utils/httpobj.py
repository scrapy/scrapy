"""Helper functions for scrapy.http objects (Request, Response)"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse
from weakref import WeakKeyDictionary, WeakValueDictionary

if TYPE_CHECKING:
    from scrapy.http import Request, Response


class _Entry:
    __slots__ = ("__weakref__", "result")

    def __init__(self, result: ParseResult):
        self.result = result


# Requests and responses hold the entry of their URL, which is dropped once
# none of them does. Results for URL strings that no request or response holds
# are kept in _string_results, for the most recently parsed ones.
_entries_by_url: WeakValueDictionary[str, _Entry] = WeakValueDictionary()
_entries_by_object: WeakKeyDictionary[Request | Response, _Entry] = WeakKeyDictionary()
_string_results: OrderedDict[str, ParseResult] = OrderedDict()
# URL strings are often parsed shortly before a request is built from them,
# e.g. link URLs, so their results must outlive a whole page worth of them.
_MAX_STRING_RESULTS = 1024


def urlparse_cached(request_or_response: Request | Response | str) -> ParseResult:
    """Return the result of parsing *request_or_response*, a
    :class:`~scrapy.Request` or :class:`~scrapy.http.Response` object or a
    URL, with :func:`urllib.parse.urlparse`.

    .. versionchanged:: VERSION
        *request_or_response* can be a URL.

    The result is cached and shared by everything with the same URL: for as
    long as a request or response with that URL exists, or else for a limited
    number of recently parsed URLs. So pass a request or response rather than
    its URL whenever you can, and prefer this function over
    :func:`urllib.parse.urlparse` when the same URL may be parsed more than
    once.
    """
    if isinstance(request_or_response, str):
        url = request_or_response
        result = _string_results.get(url)
        if result is None:
            entry = _entries_by_url.get(url)
            if entry is not None:
                return entry.result
            result = _string_results[url] = urlparse(url)
            if len(_string_results) > _MAX_STRING_RESULTS:
                _string_results.popitem(last=False)
        return result
    entry = _entries_by_object.get(request_or_response)
    if entry is None:
        url = request_or_response.url
        entry = _entries_by_url.get(url)
        if entry is None:
            result = _string_results.pop(url, None) or urlparse(url)
            entry = _entries_by_url[url] = _Entry(result)
        _entries_by_object[request_or_response] = entry
    return entry.result
