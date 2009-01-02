"""
This module provides additional LinkExtractors, apart from the ones in scrapy.link
and scrapy.link.extractors.

"""
import urlparse

from scrapy.link import Link
from scrapy.utils.url import canonicalize_url
from scrapy.utils.python import unicode_to_str
from scrapy.xpath import HtmlXPathSelector

class HTMLImageLinkExtractor(object):
    '''HTMLImageLinkExtractor objects are intended to extract image links from HTML pages
    given certain xpath locations.

    These locations can be passed in a list/tuple either when instanciating the LinkExtractor,
    or whenever you call extract_links.
    If no locations are specified in any of these places, a default pattern '//img' will be used.
    If locations are specified when instanciating the LinkExtractor, and also when calling extract_links,
    both locations will be used for that call of extract_links'''

    def __init__(self, locations=None, unique=True, canonicalize=True):
        self.locations = tuple(locations) if hasattr(locations, '__iter__') else tuple()
        self.unique = unique
        self.canonicalize = canonicalize

    def extract_from_selector(self, selector, parent=None):
        ret = []
        def _add_link(url_sel, alt_sel=None):
            url = url_sel.extract()
            alt = alt_sel.extract() if alt_sel else ('', )
            if url:
                ret.append(Link(unicode_to_str(url[0]), alt[0]))

        if selector.xmlNode.type == 'element':
            if selector.xmlNode.name == 'img':
                _add_link(selector.x('@src'), selector.x('@alt') or selector.x('@title'))
            else:
                children = selector.x('child::*')
                if len(children):
                    for child in children:
                        ret.extend(self.extract_from_selector(child, parent=selector))
                elif selector.xmlNode.name == 'a' and not parent:
                    _add_link(selector.x('@href'), selector.x('@title'))
        else:
            _add_link(selector)

        return ret

    def extract_links(self, response):
        xs = HtmlXPathSelector(response)
        base_url = xs.x('//base/@href').extract()
        base_url = unicode_to_str(base_url[0]) if base_url else unicode_to_str(response.url)

        links = []
        for location in self.locations:
            selector_res = xs.x(location)
            for selector in selector_res:
                links.extend(self.extract_from_selector(selector))

        seen, ret = set(), []
        for link in links:
            link.url = urlparse.urljoin(base_url, link.url)
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
