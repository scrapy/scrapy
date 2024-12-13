from __future__ import annotations

import platform
import sys
from importlib.metadata import version

import lxml.etree

from scrapy.settings.default_settings import LOG_VERSIONS
from scrapy.utils.ssl import get_openssl_version

_DEFAULT_COMPONENTS = ["Scrapy"] + LOG_VERSIONS


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


def scrapy_components_versions(
    components: list | None = None,
) -> list[tuple[str, str]]:
    components = components or _DEFAULT_COMPONENTS
    return [(component, _version(component)) for component in components]
