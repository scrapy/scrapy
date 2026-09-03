"""
This module contains general purpose URL functions not found in the standard
library.
"""

from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING, TypeAlias
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse

from w3lib.url import any_to_uri, parse_url, safe_url_string

from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy import Spider

UrlT: TypeAlias = str | bytes | ParseResult


def url_is_from_any_domain(url: UrlT, domains: Iterable[str]) -> bool:
    """Return True if the url belongs to any of the given domains"""
    host = parse_url(url).netloc.lower()
    if not host:
        return False
    return any((host == d) or (host.endswith(f".{d}")) for d in map(str.lower, domains))


def _spider_domains(spider: type[Spider]) -> Iterable[str]:
    yield spider.name
    allowed_domains = getattr(spider, "allowed_domains", None)
    if isinstance(allowed_domains, property):
        warnings.warn(
            f"{spider.__name__}.allowed_domains is a property. Properties "
            "cannot be evaluated on a spider class, only on a spider "
            "instance, so it will be ignored here. This affects matching "
            "URLs to spiders, e.g. in the shell, fetch and parse commands. "
            "Define allowed_domains as a plain class attribute instead.",
            stacklevel=2,
            category=UserWarning,
        )
        return
    if allowed_domains:
        yield from allowed_domains


def url_is_from_spider(url: UrlT, spider: type[Spider]) -> bool:
    """Return True if the url belongs to the given spider"""
    return url_is_from_any_domain(url, _spider_domains(spider))


def url_has_any_extension(url: UrlT, extensions: Iterable[str]) -> bool:
    """Return True if the url ends with one of the extensions provided"""
    lowercase_path = parse_url(url).path.lower()
    return any(lowercase_path.endswith(ext) for ext in extensions)


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
    - ``origin_only`` replaces the  path component with "/", also dropping
      the query component; it also strips credentials
    - ``strip_fragment`` drops any #fragment component
    """

    parsed_url = urlparse(url)
    netloc = parsed_url.netloc
    if (strip_credentials or origin_only) and (
        parsed_url.username or parsed_url.password
    ):
        netloc = netloc.split("@")[-1]

    if (
        strip_default_port
        and parsed_url.port
        and (parsed_url.scheme, parsed_url.port)
        in {
            ("http", 80),
            ("https", 443),
            ("ftp", 21),
        }
    ):
        port_suffix = f":{parsed_url.port}"
        netloc = netloc.removesuffix(port_suffix)

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


def _redirect_url(url: str, location: str | bytes) -> str:
    """Return the absolute URL that the *location* value of the ``Location``
    header of a response to a request to *url* points to."""
    target = safe_url_string(location)
    parsed_url = urlparse(url)
    if to_bytes(location).startswith(b"//"):
        # safe_url_string() may drop leading slashes of a scheme-relative URL,
        # so build the absolute URL without relying on urljoin().
        target = f"{parsed_url.scheme}://{target.lstrip('/')}"
    redirect_url = urljoin(url, target)
    if not urlparse(redirect_url).fragment and parsed_url.fragment:
        redirect_url = urljoin(redirect_url, f"#{parsed_url.fragment}")
    return redirect_url
