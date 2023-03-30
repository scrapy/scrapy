"""
Link extractor based on lxml.html
"""
import operator
from functools import partial
from urllib.parse import urljoin, urlparse

from lxml import etree
from parsel.csstranslator import HTMLTranslator
from w3lib.html import strip_html5_whitespace
from w3lib.url import canonicalize_url, safe_url_string

from scrapy.link import Link
from scrapy.linkextractors import IGNORED_EXTENSIONS
from scrapy.utils.misc import arg_to_iter, rel_has_nofollow, get_base_url
from scrapy.utils.python import unique
from scrapy.utils.response import url_is_from_any_domain, url_has_any_extension


XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
_collect_string_content = etree.XPath("string()")


def _nons(tag):
    if isinstance(tag, str) and tag.startswith('{') and tag.split('}')[0] == XHTML_NAMESPACE:
        return tag.split('}')[-1]
    return tag


def _identity(x):
    return x


class LxmlParserLinkExtractor:
    def __init__(self, tag="a", attr="href", process=None, unique=False, strip=True, canonicalized=False):
        self.scan_tag = operator.eq if callable(tag) else partial(operator.eq, tag)
        self.scan_attr = operator.eq if callable(attr) else partial(operator.eq, attr)
        self.process_attr = process if callable(process) else _identity
        self.unique = unique
        self.strip = strip
        self.link_key = operator.attrgetter("url") if canonicalized else (lambda x: canonicalize_url(x, keep_fragments=True))

    def iter_links(self, document, base_url):
        for el in document.iter(etree.Element):
            tag = _nons(el.tag)
            if not self.scan_tag(tag):
                continue
            attribs = el.attrib
            for attrib in attribs:
                if not self.scan_attr(attrib):
                    continue
                attr = attribs[attrib]
                try:
                    if self.strip:
                        attr = strip_html5_whitespace(attr)
                    attr = urljoin(base_url, attr)
                except ValueError:
                    continue  # skipping bogus links
                else:
                    url = self.process_attr(attr)
                    if url is None:
                        continue
                url = safe_url_string(url)
                url = urljoin(base_url, url)
                link = Link(url, _collect_string_content(el) or "", nofollow=rel_has_nofollow(el.get("rel")))
                yield link

    def extract_links(self, response):
        base_url = get_base_url(response)
        return self._deduplicate_if_needed(
            self.iter_links(response.selector.root, base_url)
        )

    def _process_links(self, links):
        """Normalize and filter extracted links

        The subclass should override it if necessary
        """
        return self._deduplicate_if_needed(links)

    def _deduplicate_if_needed(self, links):
        if self.unique:
            return unique(links, key=self.link_key)
        return links


class LxmlLinkExtractor:
    _csstranslator = HTMLTranslator()

    def __init__(self, allow=None, deny=None, allow_domains=None, deny_domains=None, restrict_xpaths=None, tags=('a', 'area'), attrs=('href',), canonicalize=False, unique=True, process_value=None, deny_extensions=None, restrict_css=None, strip=True, restrict_text=None):
        tags = arg_to_iter(tags)
        attrs = arg_to_iter(attrs)
        self.link_extractor = LxmlParserLinkExtractor(tag=tags.__contains__, attr=attrs.__contains__, unique=unique, process=process_value, strip=strip, canonicalized=canonicalize)
        self.allow_res = [re.compile(x) for x in arg_to_iter(allow or [])]
        self.deny_res = [re.compile(x) for x in arg_to_iter(deny or [])]
        self.allow_domains = set(arg_to_iter(allow_domains or []))
        self.deny_domains = set(arg_to_iter(deny_domains or []))
        self.restrict_xpaths = list(arg_to_iter(restrict_xpaths or []))
        self.restrict_xpaths += [self._csstranslator.css_to_xpath(x) for x in arg_to_iter(restrict_css or [])]

        self.canonicalize = canonicalize
        self.deny_extensions = {f".{x}" for x in arg_to_iter(deny_extensions or IGNORED_EXTENSIONS)}
        self.restrict_text = [re.compile(x) for x in arg_to_iter(restrict_text or [])]

    def _link_allowed(self, link):
        parsed = urlparse(link.url)
        if not parsed.scheme:
            return False
        if self.allow_res and not any(regex.search(link.url) for regex in self.allow_res):
            return False
        if self.deny_res and any(regex.search(link.url) for regex in self.deny_res):
            return False
        if self.allow_domains and not url_is_from_any_domain(parsed, self.allow_domains):
            return False
        if self.deny_domains and url_is_from_any_domain(parsed, self.deny_domains):
            return False
        if self.restrict_xpaths:
            sel = link.nested_xpath(self.restrict_xpaths)
            if not sel:
                return False
        if self.deny_extensions and url_has_any_extension(parsed, self.deny_extensions):
            return False
        if self.restrict_text and not any(regex.search(link.text) for regex in self.restrict_text):
            return False
        return True

    def _process_links(self, links):
        links = [x for x in links if self._link_allowed(x)]
        if self.canonicalize:
            for link in links:
                link.url = canonicalize_url(link.url)
        links = self.link_extractor._process_links(links)
        return links

    def extract_links(self, response):
        """Returns a list of Link objects from the specified response.
        It uses LxmlParserLinkExtractor to extract links.

        URL filtering is done through url_allowed() method.
        """
        links = self.link_extractor.extract_links(response)
        return self._process_links(links)
