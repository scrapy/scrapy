from __future__ import annotations

from collections import OrderedDict
from urllib.parse import urlparse

import pytest

from scrapy.http import Request, Response
from scrapy.utils import httpobj
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import garbage_collect


def test_urlparse_cached() -> None:
    url = "http://www.example.com/index.html"
    request1 = Request(url)
    request2 = Request(url)
    req1a = urlparse_cached(request1)
    req1b = urlparse_cached(request1)
    req2 = urlparse_cached(request2)
    urlp = urlparse(url)

    assert req1a == urlp
    assert req1a is req1b
    assert req1a is req2
    assert urlparse_cached(url) is req1a


def test_urlparse_cached_shared_by_url() -> None:
    url = "http://www.example.com/shared"
    parsed = urlparse_cached(url)
    request = Request(url)
    assert urlparse_cached(request) is parsed
    assert urlparse_cached(Response(url, request=request)) is parsed


@pytest.mark.parametrize("url_first", [True, False], ids=["url-first", "url-last"])
@pytest.mark.parametrize(
    "holders",
    [["request"], ["response"], ["request", "response"]],
    ids=["request", "response", "both"],
)
def test_urlparse_cached_lifetime(url_first: bool, holders: list[str]) -> None:
    url = f"http://www.example.com/{'-'.join(holders)}/{url_first}"
    if url_first:
        parsed = urlparse_cached(url)
    objects: list[Request | Response] = [
        Request(url) if holder == "request" else Response(url) for holder in holders
    ]
    if not url_first:
        parsed = urlparse_cached(objects[0])
    assert all(urlparse_cached(obj) is parsed for obj in objects)
    assert urlparse_cached(url) is parsed
    while objects:
        assert urlparse_cached(Request(url)) is parsed
        objects.pop(0)
        garbage_collect()
    assert urlparse_cached(Request(url)) is not parsed


def test_urlparse_cached_string_eviction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpobj, "_string_results", OrderedDict())
    monkeypatch.setattr(httpobj, "_MAX_STRING_RESULTS", 2)
    url = "http://www.example.com/evicted"
    parsed = urlparse_cached(url)
    assert urlparse_cached(url) is parsed
    urlparse_cached("http://www.example.com/evicted/1")
    urlparse_cached("http://www.example.com/evicted/2")
    assert urlparse_cached(url) is not parsed
