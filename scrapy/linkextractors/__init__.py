"""
scrapy.linkextractors

This package contains a collection of Link Extractors.

For more info see docs/topics/link-extractors.rst
"""
import re
from urllib.parse import urlparse
from warnings import warn

from parsel.csstranslator import HTMLTranslator
from w3lib.url import canonicalize_url

from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.url import (
    url_is_from_any_domain, url_has_any_extension,
)


# common file extensions that are not followed if they occur in links
IGNORED_EXTENSIONS = [
    # archives
    '7z', '7zip', 'bz2', 'rar', 'tar', 'tar.gz', 'xz', 'zip',

    # images
    'mng', 'pct', 'bmp', 'gif', 'jpg', 'jpeg', 'png', 'pst', 'psp', 'tif',
    'tiff', 'ai', 'drw', 'dxf', 'eps', 'ps', 'svg', 'cdr', 'ico',

    # audio
    'mp3', 'wma', 'ogg', 'wav', 'ra', 'aac', 'mid', 'au', 'aiff',

    # video
    '3gp', 'asf', 'asx', 'avi', 'mov', 'mp4', 'mpg', 'qt', 'rm', 'swf', 'wmv',
    'm4a', 'm4v', 'flv', 'webm',

    # office suites
    'xls', 'xlsx', 'ppt', 'pptx', 'pps', 'doc', 'docx', 'odt', 'ods', 'odg',
    'odp',

    # other
    'css', 'pdf', 'exe', 'bin', 'rss', 'dmg', 'iso', 'apk'
]


_re_type = type(re.compile("", 0))


def _matches(url, regexs):
    return any(r.search(url) for r in regexs)


def _is_valid_url(url):
    return url.split('://', 1)[0] in {'http', 'https', 'file', 'ftp'}


class FilteringLinkExtractor:

    _csstranslator = HTMLTranslator()

    def __new__(cls, *args, **kwargs):
        from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
        if (issubclass(cls, FilteringLinkExtractor) and
                not issubclass(cls, LxmlLinkExtractor)):
            warn('scrapy.linkextractors.FilteringLinkExtractor is deprecated, '
                 'please use scrapy.linkextractors.LinkExtractor instead',
                 ScrapyDeprecationWarning, stacklevel=2)
        return super(FilteringLinkExtractor, cls).__new__(cls)

    def __init__(self, link_extractor, allow, deny, allow_domains, deny_domains,
                 restrict_xpaths, canonicalize, deny_extensions, restrict_css, restrict_text):

        self.link_extractor = link_extractor

        self.allow_res = [x if isinstance(x, _re_type) else re.compile(x)
                          for x in arg_to_iter(allow)]
        self.deny_res = [x if isinstance(x, _re_type) else re.compile(x)
                         for x in arg_to_iter(deny)]

        self.allow_domains = set(arg_to_iter(allow_domains))
        self.deny_domains = set(arg_to_iter(deny_domains))

        self.restrict_xpaths = tuple(arg_to_iter(restrict_xpaths))
        self.restrict_xpaths += tuple(map(self._csstranslator.css_to_xpath,
                                          arg_to_iter(restrict_css)))

        self.canonicalize = canonicalize
        if deny_extensions is None:
            deny_extensions = IGNORED_EXTENSIONS
        self.deny_extensions = {'.' + e for e in arg_to_iter(deny_extensions)}
        self.restrict_text = [x if isinstance(x, _re_type) else re.compile(x)
                              for x in arg_to_iter(restrict_text)]

    def _link_allowed(self, link):
        if not _is_valid_url(link.url):
            return False
        if self.allow_res and not _matches(link.url, self.allow_res):
            return False
        if self.deny_res and _matches(link.url, self.deny_res):
            return False
        parsed_url = urlparse(link.url)
        if self.allow_domains and not url_is_from_any_domain(parsed_url, self.allow_domains):
            return False
        if self.deny_domains and url_is_from_any_domain(parsed_url, self.deny_domains):
            return False
        if self.deny_extensions and url_has_any_extension(parsed_url, self.deny_extensions):
            return False
        if self.restrict_text and not _matches(link.text, self.restrict_text):
            return False
        return True

    def matches(self, url):

        if self.allow_domains and not url_is_from_any_domain(url, self.allow_domains):
            return False
        if self.deny_domains and url_is_from_any_domain(url, self.deny_domains):
            return False

        allowed = (regex.search(url) for regex in self.allow_res) if self.allow_res else [True]
        denied = (regex.search(url) for regex in self.deny_res) if self.deny_res else []
        return any(allowed) and not any(denied)

    def _process_links(self, links):
        links = [x for x in links if self._link_allowed(x)]
        if self.canonicalize:
            for link in links:
                link.url = canonicalize_url(link.url)
        links = self.link_extractor._process_links(links)
        return links

    def _extract_links(self, *args, **kwargs):
        return self.link_extractor._extract_links(*args, **kwargs)


# Top-level imports
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor as LinkExtractor  # noqa: F401
