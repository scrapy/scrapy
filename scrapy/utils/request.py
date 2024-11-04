"""
This module provides some useful functions for working with
scrapy.http.Request objects
"""

from __future__ import annotations

import hashlib
import json
import warnings
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlunparse
from weakref import WeakKeyDictionary

from w3lib.http import basic_auth_header
from w3lib.url import canonicalize_url

from scrapy import Request, Spider
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    from collections.abc import Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


_fingerprint_cache: WeakKeyDictionary[
    Request, dict[tuple[tuple[bytes, ...] | None, bool], bytes]
] = WeakKeyDictionary()


def fingerprint(
    request: Request,
    *,
    include_headers: Iterable[bytes | str] | None = None,
    keep_fragments: bool = False,
) -> bytes:
    """
    Return the request fingerprint.

    The request fingerprint is a hash that uniquely identifies the resource the
    request points to. For example, take the following two urls:
    ``http://www.example.com/query?id=111&cat=222``,
    ``http://www.example.com/query?cat=222&id=111``.

    Even though those are two different URLs both point to the same resource
    and are equivalent (i.e. they should return the same response).

    Another example are cookies used to store session ids. Suppose the
    following page is only accessible to authenticated users:
    ``http://www.example.com/members/offers.html``.

    Lots of sites use a cookie to store the session id, which adds a random
    component to the HTTP Request and thus should be ignored when calculating
    the fingerprint.

    For this reason, request headers are ignored by default when calculating
    the fingerprint. If you want to include specific headers use the
    include_headers argument, which is a list of Request headers to include.

    Also, servers usually ignore fragments in urls when handling requests,
    so they are also ignored by default when calculating the fingerprint.
    If you want to include them, set the keep_fragments argument to True
    (for instance when handling requests with a headless browser).
    """
    processed_include_headers: tuple[bytes, ...] | None = None
    if include_headers:
        processed_include_headers = tuple(
            to_bytes(h.lower()) for h in sorted(include_headers)
        )
    cache = _fingerprint_cache.setdefault(request, {})
    cache_key = (processed_include_headers, keep_fragments)
    if cache_key not in cache:
        # To decode bytes reliably (JSON does not support bytes), regardless of
        # character encoding, we use bytes.hex()
        headers: dict[str, list[str]] = {}
        if processed_include_headers:
            for header in processed_include_headers:
                if header in request.headers:
                    headers[header.hex()] = [
                        header_value.hex()
                        for header_value in request.headers.getlist(header)
                    ]
        fingerprint_data = {
            "method": to_unicode(request.method),
            "url": canonicalize_url(request.url, keep_fragments=keep_fragments),
            "body": (request.body or b"").hex(),
            "headers": headers,
        }
        fingerprint_json = json.dumps(fingerprint_data, sort_keys=True)
        cache[cache_key] = hashlib.sha1(fingerprint_json.encode()).digest()  # nosec
    return cache[cache_key]


class RequestFingerprinterProtocol(Protocol):
    def fingerprint(self, request: Request) -> bytes: ...


class RequestFingerprinter:
    """Default fingerprinter.

    It takes into account a canonical version
    (:func:`w3lib.url.canonicalize_url`) of :attr:`request.url
    <scrapy.http.Request.url>` and the values of :attr:`request.method
    <scrapy.http.Request.method>` and :attr:`request.body
    <scrapy.http.Request.body>`. It then generates an `SHA1
    <https://en.wikipedia.org/wiki/SHA-1>`_ hash.

    .. seealso:: :setting:`REQUEST_FINGERPRINTER_IMPLEMENTATION`.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def __init__(self, crawler: Crawler | None = None):
        if crawler:
            implementation = crawler.settings.get(
                "REQUEST_FINGERPRINTER_IMPLEMENTATION"
            )
        else:
            implementation = "SENTINEL"

        if implementation != "SENTINEL":
            message = (
                "'REQUEST_FINGERPRINTER_IMPLEMENTATION' is a deprecated setting.\n"
                "It will be removed in a future version of Scrapy."
            )
            warnings.warn(message, category=ScrapyDeprecationWarning, stacklevel=2)
        self._fingerprint = fingerprint

    def fingerprint(self, request: Request) -> bytes:
        return self._fingerprint(request)


def request_authenticate(
    request: Request,
    username: str,
    password: str,
) -> None:
    """Authenticate the given request (in place) using the HTTP basic access
    authentication mechanism (RFC 2617) and the given username and password
    """
    warnings.warn(
        "The request_authenticate function is deprecated and will be removed in a future version of Scrapy.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    request.headers["Authorization"] = basic_auth_header(username, password)


def request_httprepr(request: Request) -> bytes:
    """Return the raw HTTP representation (as bytes) of the given request.
    This is provided only for reference since it's not the actual stream of
    bytes that will be send when performing the request (that's controlled
    by Twisted).
    """
    parsed = urlparse_cached(request)
    path = urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    s = to_bytes(request.method) + b" " + to_bytes(path) + b" HTTP/1.1\r\n"
    s += b"Host: " + to_bytes(parsed.hostname or b"") + b"\r\n"
    if request.headers:
        s += request.headers.to_string() + b"\r\n"
    s += b"\r\n"
    s += request.body
    return s


def referer_str(request: Request) -> str | None:
    """Return Referer HTTP header suitable for logging."""
    referrer = request.headers.get("Referer")
    if referrer is None:
        return referrer
    return to_unicode(referrer, errors="replace")


def request_from_dict(d: dict[str, Any], *, spider: Spider | None = None) -> Request:
    """Create a :class:`~scrapy.Request` object from a dict.

    If a spider is given, it will try to resolve the callbacks looking at the
    spider for methods with the same name.
    """
    request_cls: type[Request] = load_object(d["_class"]) if "_class" in d else Request
    kwargs = {key: value for key, value in d.items() if key in request_cls.attributes}
    if d.get("callback") and spider:
        kwargs["callback"] = _get_method(spider, d["callback"])
    if d.get("errback") and spider:
        kwargs["errback"] = _get_method(spider, d["errback"])
    return request_cls(**kwargs)


def _get_method(obj: Any, name: Any) -> Any:
    """Helper function for request_from_dict"""
    name = str(name)
    try:
        return getattr(obj, name)
    except AttributeError:
        raise ValueError(f"Method {name!r} not found in: {obj}")


def request_to_curl(request: Request) -> str:
    """
    Converts a :class:`~scrapy.Request` object to a curl command.

    :param :class:`~scrapy.Request`: Request object to be converted
    :return: string containing the curl command
    """
    method = request.method

    data = f"--data-raw '{request.body.decode('utf-8')}'" if request.body else ""

    headers = " ".join(
        f"-H '{k.decode()}: {v[0].decode()}'" for k, v in request.headers.items()
    )

    url = request.url
    cookies = ""
    if request.cookies:
        if isinstance(request.cookies, dict):
            cookie = "; ".join(f"{k}={v}" for k, v in request.cookies.items())
            cookies = f"--cookie '{cookie}'"
        elif isinstance(request.cookies, list):
            cookie = "; ".join(
                f"{list(c.keys())[0]}={list(c.values())[0]}" for c in request.cookies
            )
            cookies = f"--cookie '{cookie}'"

    curl_cmd = f"curl -X {method} {url} {data} {headers} {cookies}".strip()
    return " ".join(curl_cmd.split())
