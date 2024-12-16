from __future__ import annotations

import platform
import sys
from importlib.metadata import version
from warnings import warn

import lxml.etree

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings.default_settings import LOG_VERSIONS
from scrapy.utils.ssl import get_openssl_version

_DEFAULT_SOFTWARE = ["Scrapy"] + LOG_VERSIONS


def _version(component):
    lowercase_component = component.lower()
    if lowercase_component == "libxml2":
        return ".".join(map(str, lxml.etree.LIBXML_VERSION))
    if lowercase_component == "platform":
        return platform.platform()
    if lowercase_component == "pyopenssl":
        return get_openssl_version()
    if lowercase_component == "python":
        return sys.version.replace("\n", "- ")
    return version(component)


def get_versions(
    software: list | None = None,
) -> list[tuple[str, str]]:
    software = software or _DEFAULT_SOFTWARE
    return [(item, _version(item)) for item in software]


def scrapy_components_versions(
    components: list | None = None,
) -> list[tuple[str, str]]:
    warn(
        (
            "scrapy.utils.versions.scrapy_components_versions is deprecated, "
            "use scrapy.utils.versions.get_versions instead."
        ),
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return get_versions(components)
