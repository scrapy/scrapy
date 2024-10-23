"""
This module contains general purpose URL functions not found in the standard
library.

Some of the functions that used to be imported from this module have been moved
to the w3lib.url module. Always import those from there instead.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Union, cast
from urllib.parse import ParseResult, urldefrag, urlparse, urlunparse

# scrapy.utils.url was moved to w3lib.url and import * ensures this
# move doesn't break old code
from w3lib.url import *
from w3lib.url import _safe_chars, _unquotepath  # noqa: F401

from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy import Spider


UrlT = Union[str, bytes, ParseResult]


def url_is_from_any_domain(url: UrlT, domains: Iterable[str]) -> bool:
    """Return True if the url belongs to any of the given domains"""
    host = parse_url(url).netloc.lower()
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
    lowercase_path = parse_url(url).path.lower()
    return any(lowercase_path.endswith(ext) for ext in extensions)


def parse_url(url: UrlT, encoding: str | None = None) -> ParseResult:
    """Return urlparsed url from the given argument (which could be an already
    parsed url)
    """
    if isinstance(url, ParseResult):
        return url
    return cast(ParseResult, urlparse(to_unicode(url, encoding)))


def escape_ajax(url: str) -> str:
    """
    Return the crawlable url according to:
    https://developers.google.com/webmasters/ajax-crawling/docs/getting-started

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
    return add_or_replace_parameter(defrag, "_escaped_fragment_", frag[1:])


def add_http_if_no_scheme(url: str) -> str:
    """Add http as the default scheme if it is missing from the url."""
    match = re.match(r"^\w+://", url, flags=re.I)
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
        return any_to_uri(url)
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


def uri_handle_old_format_style(uri, params):
    """
    Formats a URI containing old-style placeholders (%s, %d, etc.) while safely handling named placeholders.

    The function:
    1. Escapes non-named or invalid named placeholders (e.g., %s, %d, %(missing)s).
    2. Replaces valid named placeholders using old-style formatting.
    3. Restores non-named placeholders as they originally appeared in the URI.

    Parameters:
        uri (str): The URI string potentially containing old-style format specifiers.
        params (dict): A dictionary containing values to replace named format specifiers.

    Returns:
        str: The formatted URI with valid named placeholders replaced.
    """
    escaped_uri, placeholders = _escape_non_named_placeholders(uri)

    try:
        # Step 2: Perform old-style formatting using valid named placeholders from `params`
        formatted_uri = escaped_uri % params
    except KeyError as error:
        raise KeyError(f"Error formatting URI: {error}")

    # Step 3: Restore non-named placeholders in the formatted URI
    return _restore_placeholders(formatted_uri, placeholders)


def _escape_non_named_placeholders(uri):
    """
    Identifies and replaces non-named placeholders with markers.

    Parameters:
        uri (str): The URI containing old-style format specifiers.

    Returns:
        tuple: A tuple containing the escaped URI and a list of original placeholders.
    """
    placeholders = []
    placeholder_marker = "__PLACEHOLDER__"

    def _store_placeholder(match):
        """Store and replace non-named placeholders."""
        placeholders.append(match.group(0))
        return f"{placeholder_marker}{len(placeholders) - 1}___"

    escaped_uri = re.sub(r"%(?!\(\w+\))", _store_placeholder, uri)
    return escaped_uri, placeholders


def _restore_placeholders(uri, placeholders):
    """
    Restores the original non-named placeholders into the formatted URI.

    Parameters:
        uri (str): The formatted URI containing placeholder markers.
        placeholders (list): List of original placeholders to restore.

    Returns:
        str: The URI with all placeholders restored.
    """
    placeholder_marker = "__PLACEHOLDER__"
    for index, placeholder in enumerate(placeholders):
        uri = uri.replace(f"{placeholder_marker}{index}___", placeholder, 1)
    return uri
