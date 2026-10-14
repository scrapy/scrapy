"""
scrapy.linkextractors

This package contains a collection of Link Extractors.

For more info see docs/topics/link-extractors.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from re import Pattern

IGNORED_EXTENSIONS = [
    # archives
    "7z",
    "7zip",
    "bz2",
    "rar",
    "tar",
    "tar.gz",
    "xz",
    "zip",
    # images
    "mng",
    "pct",
    "bmp",
    "gif",
    "jpg",
    "jpeg",
    "png",
    "pst",
    "psp",
    "tif",
    "tiff",
    "ai",
    "drw",
    "dxf",
    "eps",
    "ps",
    "svg",
    "cdr",
    "ico",
    "webp",
    # audio
    "mp3",
    "wma",
    "ogg",
    "wav",
    "ra",
    "aac",
    "mid",
    "au",
    "aiff",
    # video
    "3gp",
    "asf",
    "asx",
    "avi",
    "mov",
    "mp4",
    "mpg",
    "qt",
    "rm",
    "swf",
    "wmv",
    "m4a",
    "m4v",
    "flv",
    "webm",
    # office suites
    "xls",
    "xlsm",
    "xlsx",
    "xltm",
    "xltx",
    "potm",
    "potx",
    "ppt",
    "pptm",
    "pptx",
    "pps",
    "doc",
    "docb",
    "docm",
    "docx",
    "dotm",
    "dotx",
    "odt",
    "ods",
    "odg",
    "odp",
    # other
    "css",
    "pdf",
    "exe",
    "bin",
    "rss",
    "dmg",
    "iso",
    "apk",
    "jar",
    "sh",
    "rb",
    "js",
    "hta",
    "bat",
    "cpl",
    "msi",
    "msp",
    "py",
]
"""File extensions of files that are usually not worth following, and hence the
default value of the ``deny_extensions`` parameter of :class:`LinkExtractor
<scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`."""


SUPPORTED_SCHEMES = [
    "data",
    "file",
    "ftp",
    "http",
    "https",
    "s3",
]
"""URL schemes that Scrapy can download out of the box, and hence the default
value of the ``schemes`` parameter of :class:`LinkExtractor
<scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`."""


def _matches(url: str, regexs: Iterable[Pattern[str]]) -> bool:
    return any(r.search(url) for r in regexs)


# Top-level imports
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor as LinkExtractor

__all__ = [
    "IGNORED_EXTENSIONS",
    "SUPPORTED_SCHEMES",
    "LinkExtractor",
]
