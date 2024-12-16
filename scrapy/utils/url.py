"""
This module contains general purpose URL functions not found in the standard
library.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Union
from urllib.parse import ParseResult, urldefrag, urlparse, urlunparse

from w3lib.url import add_or_replace_parameter as _add_or_replace_parameter
from w3lib.url import add_or_replace_parameters as _add_or_replace_parameters
from w3lib.url import any_to_uri as _any_to_uri
from w3lib.url import canonicalize_url as _canonicalize_url
from w3lib.url import file_uri_to_path as _file_uri_to_path
from w3lib.url import is_url as _is_url
from w3lib.url import parse_data_uri as _parse_data_uri
from w3lib.url import parse_url as _parse_url
from w3lib.url import path_to_file_uri as _path_to_file_uri
from w3lib.url import safe_download_url as _safe_download_url
from w3lib.url import safe_url_string as _safe_url_string
from w3lib.url import url_query_cleaner as _url_query_cleaner
from w3lib.url import url_query_parameter as _url_query_parameter

from scrapy.utils.decorators import deprecated

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy import Spider

add_or_replace_parameter = deprecated("w3lib.url.add_or_replace_parameter")(
    _add_or_replace_parameter
)
add_or_replace_parameters = deprecated("w3lib.url.add_or_replace_parameters")(
    _add_or_replace_parameters
)
any_to_uri = deprecated("w3lib.url.any_to_uri")(_any_to_uri)
canonicalize_url = deprecated("w3lib.url.canonicalize_url")(_canonicalize_url)
file_uri_to_path = deprecated("w3lib.url.file_uri_to_path")(_file_uri_to_path)
is_url = deprecated("w3lib.url.is_url")(_is_url)
parse_data_uri = deprecated("w3lib.url.parse_data_uri")(_parse_data_uri)
path_to_file_uri = deprecated("w3lib.url.path_to_file_uri")(_path_to_file_uri)
safe_download_url = deprecated("w3lib.url.safe_download_url")(_safe_download_url)
safe_url_string = deprecated("w3lib.url.safe_url_string")(_safe_url_string)
url_query_cleaner = deprecated("w3lib.url.url_query_cleaner")(_url_query_cleaner)
url_query_parameter = deprecated("w3lib.url.url_query_parameter")(_url_query_parameter)


parse_url = deprecated("w3lib.url.parse_url")(_parse_url)

UrlT = Union[str, bytes, ParseResult]


def url_is_from_any_domain(url: UrlT, domains: Iterable[str]) -> bool:
    """Return True if the url belongs to any of the given domains"""
    host = _parse_url(url).netloc.lower()
    if not host:
        return False
    domains = [d.lower() for d in domains]
    return any((host == d) or (host.endswith(f".{d}")) for d in domains)


def url_is_from_spider(url: UrlT, spider: type[Spider]) -> bool:
    """Return True if the url belongs to the given spider"""
    return url_is_from_any_domain(
        url, [spider.name] + list(getattr(spider, "allowed_domains", []))
    )


def url_has_any_extension(url: UrlT, extensions: Iterable[str]) -> bool:
    """Return True if the url ends with one of the extensions provided"""
    lowercase_path = _parse_url(url).path.lower()
    return any(lowercase_path.endswith(ext) for ext in extensions)


def escape_ajax(url: str) -> str:
    """
    Return the crawlable url

    >>> escape_ajax("www.example.com/ajax.html#!key=value")
    'www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html?k1=v1&k2=v2#!key=value")
    'www.example.com/ajax.html?k1=v1&k2=v2&_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html?#!key=value")
    'www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html#!")
    'www.example.com/ajax.html?_escaped_fragment_='

    URLs that are not "AJAX crawlable" (according to Google) returned as-is:

    >>> escape_ajax("www.example.com/ajax.html#key=value")
    'www.example.com/ajax.html#key=value'
    >>> escape_ajax("www.example.com/ajax.html#")
    'www.example.com/ajax.html#'
    >>> escape_ajax("www.example.com/ajax.html")
    'www.example.com/ajax.html'
    """
    defrag, frag = urldefrag(url)
    if not frag.startswith("!"):
        return url
    return _add_or_replace_parameter(defrag, "_escaped_fragment_", frag[1:])


def add_http_if_no_scheme(url: str) -> str:
    """Add http as the default scheme if it is missing from the url."""
    match = re.match(r"^\w+://", url, flags=re.IGNORECASE)
    if not match:
        parts = urlparse(url)
        scheme = "http:" if parts.netloc else "http://"
        url = scheme + url

    return url


def _is_posix_path(string: str) -> bool:
    return bool(
        re.match(
            r"""
            ^                   # start with...
            (
                \.              # ...a single dot,
                (
                    \. | [^/\.]+  # optionally followed by
                )?                # either a second dot or some characters
                |
                ~   # $HOME
            )?      # optional match of ".", ".." or ".blabla"
            /       # at least one "/" for a file path,
            .       # and something after the "/"
            """,
            string,
            flags=re.VERBOSE,
        )
    )


def _is_windows_path(string: str) -> bool:
    return bool(
        re.match(
            r"""
            ^
            (
                [a-z]:\\
                | \\\\
            )
            """,
            string,
            flags=re.IGNORECASE | re.VERBOSE,
        )
    )


def _is_filesystem_path(string: str) -> bool:
    return _is_posix_path(string) or _is_windows_path(string)


def guess_scheme(url: str) -> str:
    """Add an URL scheme if missing: file:// for filepath-like input or
    http:// otherwise."""
    if _is_filesystem_path(url):
        return _any_to_uri(url)
    return add_http_if_no_scheme(url)


def strip_url(
    url: str,
    strip_credentials: bool = True,
    strip_default_port: bool = True,
    origin_only: bool = False,
    strip_fragment: bool = True,
) -> str:
    """Strip URL string from some of its components:

    - ``strip_credentials`` removes "user:password@"
    - ``strip_default_port`` removes ":80" (resp. ":443", ":21")
      from http:// (resp. https://, ftp://) URLs
    - ``origin_only`` replaces path component with "/", also dropping
      query and fragment components ; it also strips credentials
    - ``strip_fragment`` drops any #fragment component
    """

    parsed_url = urlparse(url)
    netloc = parsed_url.netloc
    if (strip_credentials or origin_only) and (
        parsed_url.username or parsed_url.password
    ):
        netloc = netloc.split("@")[-1]
    if strip_default_port and parsed_url.port:
        if (parsed_url.scheme, parsed_url.port) in (
            ("http", 80),
            ("https", 443),
            ("ftp", 21),
        ):
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
