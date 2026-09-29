from __future__ import annotations

import gc
from urllib.parse import urlparse

from scrapy.http import Request, Response
from scrapy.utils.httpobj import urlparse_cached


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


def test_urlparse_cached_released() -> None:
    url = "http://www.example.com/released"
    request = Request(url)
    parsed = urlparse_cached(request)
    response = Response(url)
    urlparse_cached(response)
    del request
    gc.collect()
    assert urlparse_cached(Request(url)) is parsed
    del response
    gc.collect()
    assert urlparse_cached(Request(url)) is not parsed
