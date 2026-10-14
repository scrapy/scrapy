from __future__ import annotations

import platform
import sys
from importlib.metadata import version

import lxml.etree
import OpenSSL.SSL
import OpenSSL.version

from scrapy.settings.default_settings import LOG_VERSIONS

_DEFAULT_SOFTWARE: list[str] = ["Scrapy", *LOG_VERSIONS]


def _get_openssl_version() -> str:
    system_openssl_bytes = OpenSSL.SSL.SSLeay_version(OpenSSL.SSL.SSLEAY_VERSION)
    system_openssl = system_openssl_bytes.decode("ascii", errors="replace")
    return f"{OpenSSL.version.__version__} ({system_openssl})"


def _version(item: str) -> str:
    lowercase_item = item.lower()
    if lowercase_item == "libxml2":
        return ".".join(map(str, lxml.etree.LIBXML_VERSION))
    if lowercase_item == "platform":
        return platform.platform()
    if lowercase_item == "pyopenssl":
        return _get_openssl_version()
    if lowercase_item == "python":
        return sys.version.replace("\n", "- ")
    return version(item)


def get_versions(
    software: list[str] | None = None,
) -> list[tuple[str, str]]:
    software = software or _DEFAULT_SOFTWARE
    return [(item, _version(item)) for item in software]
