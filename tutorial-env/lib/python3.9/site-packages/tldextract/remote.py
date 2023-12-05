"""tldextract helpers for testing and fetching remote resources."""

from __future__ import annotations

import re
from collections.abc import Callable
from ipaddress import AddressValueError, IPv6Address
from urllib.parse import scheme_chars

inet_pton: Callable[[int, str], bytes] | None
try:
    from socket import AF_INET, AF_INET6, inet_pton  # Availability: Unix, Windows.
except ImportError:
    inet_pton = None

IP_RE = re.compile(
    r"^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.)"
    r"{3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
)

scheme_chars_set = set(scheme_chars)


def lenient_netloc(url: str) -> str:
    """Extract the netloc of a URL-like string.

    Similar to the netloc attribute returned by
    urllib.parse.{urlparse,urlsplit}, but extract more leniently, without
    raising errors.
    """
    after_userinfo = (
        _schemeless_url(url)
        .partition("/")[0]
        .partition("?")[0]
        .partition("#")[0]
        .rpartition("@")[-1]
    )

    if after_userinfo and after_userinfo[0] == "[":
        maybe_ipv6 = after_userinfo.partition("]")
        if maybe_ipv6[1] == "]":
            return f"{maybe_ipv6[0]}]"

    hostname = after_userinfo.partition(":")[0].strip()
    without_root_label = hostname.rstrip(".\u3002\uff0e\uff61")
    return without_root_label


def _schemeless_url(url: str) -> str:
    double_slashes_start = url.find("//")
    if double_slashes_start == 0:
        return url[2:]
    if (
        double_slashes_start < 2
        or not url[double_slashes_start - 1] == ":"
        or set(url[: double_slashes_start - 1]) - scheme_chars_set
    ):
        return url
    return url[double_slashes_start + 2 :]


def looks_like_ip(
    maybe_ip: str, pton: Callable[[int, str], bytes] | None = inet_pton
) -> bool:
    """Check whether the given str looks like an IP address."""
    if not maybe_ip[0].isdigit():
        return False

    if pton is not None:
        try:
            pton(AF_INET, maybe_ip)
            return True
        except OSError:
            return False
    return IP_RE.fullmatch(maybe_ip) is not None


def looks_like_ipv6(
    maybe_ip: str, pton: Callable[[int, str], bytes] | None = inet_pton
) -> bool:
    """Check whether the given str looks like an IPv6 address."""
    if pton is not None:
        try:
            pton(AF_INET6, maybe_ip)
            return True
        except OSError:
            return False
    try:
        IPv6Address(maybe_ip)
    except AddressValueError:
        return False
    return True
