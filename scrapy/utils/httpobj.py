"""Helper functions for scrapy.http objects (Request, Response)"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse
from weakref import WeakKeyDictionary, WeakValueDictionary

if TYPE_CHECKING:
    from scrapy.http import Request, Response


class _Entry:
    __slots__ = ("__weakref__", "result")

    def __init__(self, result: ParseResult):
        self.result = result


# An entry lives as long as something holds it: a request or response with its
# URL, or the LRU cache of URL strings.
_entries_by_url: WeakValueDictionary[str, _Entry] = WeakValueDictionary()
_entries_by_object: WeakKeyDictionary[Request | Response, _Entry] = WeakKeyDictionary()


def _entry(url: str) -> _Entry:
    entry = _entries_by_url.get(url)
    if entry is None:
        entry = _entries_by_url[url] = _Entry(urlparse(url))
    return entry


# URL strings are often parsed shortly before a request is built from them,
# e.g. link URLs, so their entries must outlive a whole page worth of them.
_string_entry = lru_cache(maxsize=1024)(_entry)


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
        return _string_entry(request_or_response).result
    entry = _entries_by_object.get(request_or_response)
    if entry is None:
        entry = _entries_by_object[request_or_response] = _entry(
            request_or_response.url
        )
    return entry.result
