"""
Link extractor based on lxml.html
"""
import operator
from functools import partial
from urllib.parse import urljoin

import lxml.etree as etree
from w3lib.html import strip_html5_whitespace
from w3lib.url import canonicalize_url, safe_url_string

from scrapy.link import Link
from scrapy.linkextractors import FilteringLinkExtractor
from scrapy.utils.misc import arg_to_iter, rel_has_nofollow
from scrapy.utils.python import unique as unique_list
from scrapy.utils.response import get_base_url


# from lxml/src/lxml/html/__init__.py
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

_collect_string_content = etree.XPath("string()")


def _nons(tag):
    if isinstance(tag, str):
        if tag[0] == '{' and tag[1:len(XHTML_NAMESPACE) + 1] == XHTML_NAMESPACE:
            return tag.split('}')[-1]
    return tag


def _identity(x):
    return x


def _canonicalize_link_url(link):
    return canonicalize_url(link.url, keep_fragments=True)


class LxmlParserLinkExtractor:
    def __init__(
        self, tag="a", attr="href", process=None, unique=False, strip=True, canonicalized=False
    ):
        self.scan_tag = tag if callable(tag) else partial(operator.eq, tag)
        self.scan_attr = attr if callable(attr) else partial(operator.eq, attr)
        self.process_attr = process if callable(process) else _identity
        self.unique = unique
        self.strip = strip
        self.link_key = operator.attrgetter("url") if canonicalized else _canonicalize_link_url

    def _iter_links(self, document):
        for el in document.iter(etree.Element):
            if not self.scan_tag(_nons(el.tag)):
                continue
            attribs = el.attrib
            for attrib in attribs:
                if not self.scan_attr(attrib):
                    continue
                yield (el, attrib, attribs[attrib])

    def _extract_links(self, selector, response_url, response_encoding, base_url):
        links = []
        # hacky way to get the underlying lxml parsed document
        for el, attr, attr_val in self._iter_links(selector.root):
            # pseudo lxml.html.HtmlElement.make_links_absolute(base_url)
            try:
                if self.strip:
                    attr_val = strip_html5_whitespace(attr_val)
                attr_val = urljoin(base_url, attr_val)
            except ValueError:
                continue  # skipping bogus links
            else:
                url = self.process_attr(attr_val)
                if url is None:
                    continue
            url = safe_url_string(url, encoding=response_encoding)
            # to fix relative links after process_value
            url = urljoin(response_url, url)
            link = Link(url, _collect_string_content(el) or u'',
                        nofollow=rel_has_nofollow(el.get('rel')))
            links.append(link)
        return self._deduplicate_if_needed(links)

    def extract_links(self, response):
        base_url = get_base_url(response)
        return self._extract_links(response.selector, response.url, response.encoding, base_url)

    def _process_links(self, links):
        """ Normalize and filter extracted links

        The subclass should override it if neccessary
        """
        return self._deduplicate_if_needed(links)

    def _deduplicate_if_needed(self, links):
        if self.unique:
            return unique_list(links, key=self.link_key)
        return links


class LxmlLinkExtractor(FilteringLinkExtractor):

    def __init__(
        self,
        allow=(),
        deny=(),
        allow_domains=(),
        deny_domains=(),
        restrict_xpaths=(),
        tags=('a', 'area'),
        attrs=('href',),
        canonicalize=False,
        unique=True,
        process_value=None,
        deny_extensions=None,
        restrict_css=(),
        strip=True,
        restrict_text=None,
    ):
        tags, attrs = set(arg_to_iter(tags)), set(arg_to_iter(attrs))
        lx = LxmlParserLinkExtractor(
            tag=partial(operator.contains, tags),
            attr=partial(operator.contains, attrs),
            unique=unique,
            process=process_value,
            strip=strip,
            canonicalized=canonicalize
        )
        super(LxmlLinkExtractor, self).__init__(
            link_extractor=lx,
            allow=allow,
            deny=deny,
            allow_domains=allow_domains,
            deny_domains=deny_domains,
            restrict_xpaths=restrict_xpaths,
            restrict_css=restrict_css,
            canonicalize=canonicalize,
            deny_extensions=deny_extensions,
            restrict_text=restrict_text,
        )

    def extract_links(self, response):
        """Returns a list of :class:`~scrapy.link.Link` objects from the
        specified :class:`response <scrapy.http.Response>`.

        Only links that match the settings passed to the ``__init__`` method of
        the link extractor are returned.

        Duplicate links are omitted.
        """
        base_url = get_base_url(response)
        if self.restrict_xpaths:
            docs = [
                subdoc
                for x in self.restrict_xpaths
                for subdoc in response.xpath(x)
            ]
        else:
            docs = [response.selector]
        all_links = []
        for doc in docs:
            links = self._extract_links(doc, response.url, response.encoding, base_url)
            all_links.extend(self._process_links(links))
        return unique_list(all_links)
