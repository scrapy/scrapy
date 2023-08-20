"""
scrapy.linkextractors

This package contains a collection of Link Extractors.

For more info see docs/topics/link-extractors.rst
"""
import re

# common file extensions that are not followed if they occur in links
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
    "xlsx",
    "ppt",
    "pptx",
    "pps",
    "doc",
    "docx",
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
]


_re_type = type(re.compile("", 0))


def _matches(url, regexs):
    return any(r.search(url) for r in regexs)


def _is_valid_url(url):
    return url.split("://", 1)[0] in {"http", "https", "file", "ftp"}


# Top-level imports
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor as LinkExtractor
