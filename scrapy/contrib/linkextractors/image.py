"""
This module implements the HtmlImageLinkExtractor for extracting 
image links only.
"""

from urlparse import urljoin
from scrapy.link import Link
from scrapy.utils.url import canonicalize_url
from scrapy.utils.python import unicode_to_str, flatten
from scrapy.selector.libxml2sel import XPathSelectorList, HtmlXPathSelector

class HTMLImageLinkExtractor(object):
    '''HTMLImageLinkExtractor objects are intended to extract image links from HTML pages
    given certain xpath locations.

    These locations can be passed in a list/tuple either when instanciating the LinkExtractor,
    or whenever you call extract_links.
    If no locations are specified in any of these places, a default pattern '//img' will be used.
    If locations are specified when instanciating the LinkExtractor, and also when calling extract_links,
    both locations will be used for that call of extract_links'''

    def __init__(self, locations=None, unique=True, canonicalize=True):
        self.locations = flatten([locations])
        self.unique = unique
        self.canonicalize = canonicalize

    def extract_from_selector(self, selector, encoding, parent=None):
        ret = []
        def _add_link(url_sel, alt_sel=None):
            url = flatten([url_sel.extract()])
            alt = flatten([alt_sel.extract()]) if alt_sel else (u'', )
            if url:
                ret.append(Link(unicode_to_str(url[0], encoding), alt[0]))

        if selector.xmlNode.type == 'element':
            if selector.xmlNode.name == 'img':
                _add_link(selector.select('@src'), selector.select('@alt') or \
                          selector.select('@title'))
            else:
                children = selector.select('child::*')
                if len(children):
                    for child in children:
                        ret.extend(self.extract_from_selector(child, encoding, parent=selector))
                elif selector.xmlNode.name == 'a' and not parent:
                    _add_link(selector.select('@href'), selector.select('@title'))
        else:
            _add_link(selector)

        return ret

    def extract_links(self, response):
        xs = HtmlXPathSelector(response)
        base_url = xs.select('//base/@href').extract()
        base_url = urljoin(response.url, base_url[0].encode(response.encoding)) if base_url else response.url

        links = []
        for location in self.locations:
            if isinstance(location, basestring):
                selectors = xs.select(location)
            elif isinstance(location, (XPathSelectorList, HtmlXPathSelector)):
                selectors = [location] if isinstance(location, HtmlXPathSelector) else location
            else:
                continue

            for selector in selectors:
                links.extend(self.extract_from_selector(selector, response.encoding))

        seen, ret = set(), []
        for link in links:
            link.url = urljoin(base_url, link.url)
            if self.unique:
                if link.url in seen:
                    continue
                else:
                    seen.add(link.url)
            if self.canonicalize:
                link.url = canonicalize_url(link.url)
            ret.append(link)

        return ret

    def matches(self, url):
        return False
