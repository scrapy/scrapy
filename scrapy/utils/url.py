"""
This module contains general purpose URL functions not found in the standard
library.
"""

from __future__ import annotations

import re
import warnings
from importlib import import_module
from typing import TYPE_CHECKING, Union
from urllib.parse import ParseResult, urldefrag, urlparse, urlunparse
from warnings import warn

from w3lib.url import __all__ as _public_w3lib_objects
from w3lib.url import add_or_replace_parameter as _add_or_replace_parameter
from w3lib.url import any_to_uri as _any_to_uri
from w3lib.url import parse_url as _parse_url

from scrapy.exceptions import ScrapyDeprecationWarning


def __getattr__(name: str):
    if name in ("_unquotepath", "_safe_chars", "parse_url", *_public_w3lib_objects):
        obj_type = "attribute" if name == "_safe_chars" else "function"
        warnings.warn(
            f"The scrapy.utils.url.{name} {obj_type} is deprecated, use w3lib.url.{name} instead.",
            ScrapyDeprecationWarning,
        )
        return getattr(import_module("w3lib.url"), name)
    raise AttributeError


if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy import Spider

UrlT = Union[str, bytes, ParseResult]


def url_is_from_any_domain(url: UrlT, domains: Iterable[str]) -> bool:
    """Return True if the url belongs to any of the given domains"""
    host = _parse_url(url).netloc.lower()
    if not host:
        return False
    domains = [d.lower() for d in domains]
    return any(host == d or host.endswith(f".{d}") for d in domains)


def url_is_from_spider(url: UrlT, spider: type[Spider]) -> bool:
    """Return True if the url belongs to the given spider"""
    return url_is_from_any_domain(
        url, [spider.name, *getattr(spider, "allowed_domains", [])]
    )


def url_has_any_extension(url: UrlT, extensions: Iterable[str]) -> bool:
    """Return True if the url ends with one of the extensions provided"""
    return any(_parse_url(url).path.lower().endswith(ext) for ext in extensions)


def escape_ajax(url: str) -> str:
    """
    Return the crawlable url
    """
    warn(
        "escape_ajax() is deprecated and will be removed in a future Scrapy version.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    defrag, frag = urldefrag(url)
    if not frag.startswith("!"):
        return url
    return _add_or_replace_parameter(defrag, "_escaped_fragment_", frag[1:])


def add_http_if_no_scheme(url: str) -> str:
    """Add http as the default scheme if it is missing from the url."""
    if not re.match(r"^\w+://", url, flags=re.IGNORECASE):
        parts = urlparse(url)
        scheme = "http:" if parts.netloc else "http://"
        url = scheme + url
    return url


def _is_posix_path(string: str) -> bool:
    return bool(re.match(r"^(\.((\.|[^/\.]+)?)|~)?/.+", string, flags=re.VERBOSE))


def _is_windows_path(string: str) -> bool:
    return bool(re.match(r"^([a-z]:\\|\\\\)", string, flags=re.IGNORECASE | re.VERBOSE))


def _is_filesystem_path(string: str) -> bool:
    return _is_posix_path(string) or _is_windows_path(string)


def guess_scheme(url: str) -> str:
    """Add an URL scheme if missing: file:// for filepath-like input or
    http:// otherwise."""
    return _any_to_uri(url) if _is_filesystem_path(url) else add_http_if_no_scheme(url)


def strip_url(
    url: str,
    strip_credentials: bool = True,
    strip_default_port: bool = True,
    origin_only: bool = False,
    strip_fragment: bool = True,
) -> str:
    """Strip URL string from some of its components"""
    parsed_url = urlparse(url)
    netloc = parsed_url.netloc.split("@")[-1] if (strip_credentials or origin_only) and (parsed_url.username or parsed_url.password) else parsed_url.netloc

    if strip_default_port and parsed_url.port and (parsed_url.scheme, parsed_url.port) in (("http", 80), ("https", 443), ("ftp", 21)):
        netloc = netloc.replace(f":{parsed_url.port}", "")

    return urlunparse(
        (
            parsed_url.scheme,
            netloc,
            "/" if origin_only else parsed_url.path,
            "" if origin_only else parsed_url.params,
            "" if origin_only else parsed_url.query,
            "" if strip_fragment else parsed_url.fragment,
        )
    )
