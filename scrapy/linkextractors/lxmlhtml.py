"""
Link extractor based on lxml.html
"""

import re
from six.moves.urllib.parse import urlparse, urljoin

import lxml.etree as etree

from scrapy.selector import Selector
from scrapy.link import Link
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import unique as unique_list, str_to_unicode
from scrapy.linkextractors import FilteringLinkExtractor
from scrapy.utils.response import get_base_url


# from lxml/src/lxml/html/__init__.py
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

_collect_string_content = etree.XPath("string()")

def _nons(tag):
    if isinstance(tag, basestring):
        if tag[0] == '{' and tag[1:len(XHTML_NAMESPACE)+1] == XHTML_NAMESPACE:
            return tag.split('}')[-1]
    return tag


class LxmlParserLinkExtractor(object):
    def __init__(self, tag="a", attr="href", process=None, unique=False):
        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
        self.process_attr = process if callable(process) else lambda v: v
        self.unique = unique

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
        for el, attr, attr_val in self._iter_links(selector._root):
            # pseudo lxml.html.HtmlElement.make_links_absolute(base_url)
            try:
                attr_val = urljoin(base_url, attr_val)
            except ValueError:
                continue # skipping bogus links
            else:
                url = self.process_attr(attr_val)
                if url is None:
                    continue
            if isinstance(url, unicode):
                url = url.encode(response_encoding)
            # to fix relative links after process_value
            url = urljoin(response_url, url)
            link = Link(url, _collect_string_content(el) or u'',
                nofollow=True if el.get('rel') == 'nofollow' else False)
            links.append(link)

        return unique_list(links, key=lambda link: link.url) \
                if self.unique else links

    def extract_links(self, response):
        html = Selector(response)
        base_url = get_base_url(response)
        return self._extract_links(html, response.url, response.encoding, base_url)

    def _process_links(self, links):
        """ Normalize and filter extracted links

        The subclass should override it if neccessary
        """
        links = unique_list(links, key=lambda link: link.url) if self.unique else links
        return links


class LxmlLinkExtractor(FilteringLinkExtractor):

    def __init__(self, allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths=(),
                 tags=('a', 'area'), attrs=('href',), canonicalize=True,
                 unique=True, process_value=None, deny_extensions=None, restrict_css=()):
        tags, attrs = set(arg_to_iter(tags)), set(arg_to_iter(attrs))
        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs
        lx = LxmlParserLinkExtractor(tag=tag_func, attr=attr_func,
            unique=unique, process=process_value)

        super(LxmlLinkExtractor, self).__init__(lx, allow=allow, deny=deny,
            allow_domains=allow_domains, deny_domains=deny_domains,
            restrict_xpaths=restrict_xpaths, restrict_css=restrict_css,
            canonicalize=canonicalize, deny_extensions=deny_extensions)

    def extract_links(self, response):
        html = Selector(response)
        base_url = get_base_url(response)
        if self.restrict_xpaths:
            docs = [subdoc
                    for x in self.restrict_xpaths
                    for subdoc in html.xpath(x)]
        else:
            docs = [html]
        all_links = []
        for doc in docs:
            links = self._extract_links(doc, response.url, response.encoding, base_url)
            all_links.extend(self._process_links(links))
        return unique_list(all_links)

