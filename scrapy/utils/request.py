"""
This module provides some useful functions for working with
scrapy.Request objects
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Iterable, Protocol
from urllib.parse import urlunparse
from weakref import WeakKeyDictionary

from w3lib.url import canonicalize_url

from scrapy import Request, Spider
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


class FingerprintBuilder:
    """Helper to assemble request fingerprint data and hash."""

    def __init__(
        self,
        request: Request,
        processed_headers: tuple[bytes, ...] | None,
        keep_fragments: bool,
    ) -> None:
        self.request = request
        self.processed_headers = processed_headers
        self.keep_fragments = keep_fragments

    def _build_headers(self) -> dict[str, list[str]]:
        headers: dict[str, list[str]] = {}
        if not self.processed_headers:
            return headers

        for header in self.processed_headers:
            if header in self.request.headers:
                headers[header.hex()] = [
                    header_value.hex()
                    for header_value in self.request.headers.getlist(header)
                ]
        return headers

    def build_payload(self) -> dict[str, Any]:
        return {
            "method": to_unicode(self.request.method),
            "url": canonicalize_url(
                self.request.url, keep_fragments=self.keep_fragments
            ),
            "body": (self.request.body or b"").hex(),
            "headers": self._build_headers(),
        }

    def build_hash(self) -> bytes:
        fingerprint_json = json.dumps(self.build_payload(), sort_keys=True)
        return hashlib.sha1(fingerprint_json.encode()).digest()  # noqa: S324


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
    return _DEFAULT_FINGERPRINTER.fingerprint(
        request,
        include_headers=include_headers,
        keep_fragments=keep_fragments,
    )


class RequestFingerprinterProtocol(Protocol):
    def fingerprint(self, request: Request) -> bytes: ...


class RequestFingerprinter:
    """Default fingerprinter.

    It takes into account a canonical version
    (:func:`w3lib.url.canonicalize_url`) of :attr:`request.url
    <scrapy.Request.url>` and the values of :attr:`request.method
    <scrapy.Request.method>` and :attr:`request.body
    <scrapy.Request.body>`. It then generates an `SHA1
    <https://en.wikipedia.org/wiki/SHA-1>`_ hash.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def __init__(self, crawler: Crawler | None = None):
        self._cache: WeakKeyDictionary[
            Request, dict[tuple[tuple[bytes, ...] | None, bool], bytes]
        ] = WeakKeyDictionary()

    def _process_headers(
        self, include_headers: Iterable[bytes | str] | None
    ) -> tuple[bytes, ...] | None:
        if include_headers is None:
            return None
        return tuple(to_bytes(h.lower()) for h in sorted(include_headers))

    def fingerprint(
        self,
        request: Request,
        *,
        include_headers: Iterable[bytes | str] | None = None,
        keep_fragments: bool = False,
    ) -> bytes:
        processed_include_headers = self._process_headers(include_headers)
        cache = self._cache.setdefault(request, {})
        cache_key = (processed_include_headers, keep_fragments)
        if cache_key not in cache:
            cache[cache_key] = FingerprintBuilder(
                request,
                processed_include_headers,
                keep_fragments,
            ).build_hash()
        return cache[cache_key]


_DEFAULT_FINGERPRINTER = RequestFingerprinter()

_fingerprint_cache = _DEFAULT_FINGERPRINTER._cache


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
                f"{next(iter(c.keys()))}={next(iter(c.values()))}"
                for c in request.cookies
            )
            cookies = f"--cookie '{cookie}'"

    curl_cmd = f"curl -X {method} {url} {data} {headers} {cookies}".strip()
    return " ".join(curl_cmd.split())
