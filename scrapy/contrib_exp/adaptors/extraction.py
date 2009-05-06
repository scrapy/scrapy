"""
Adaptors related with extraction of data
"""

import urlparse
import re
from scrapy import log
from scrapy.http import Response
from scrapy.utils.url import is_url
from scrapy.utils.response import get_base_url
from scrapy.utils.python import flatten, unicode_to_str
from scrapy.xpath.selector import XPathSelector, XPathSelectorList
from scrapy.contrib.link_extractors import HTMLImageLinkExtractor

def extract(location, adaptor_args=None):
    """
    This adaptor tries to extract data from the given locations.
    Any XPathSelector in it will be extracted, and any other data
    will be added as-is to the result.

    If an XPathSelector is a text/cdata node, and `use_unquote`
    is True, that selector will be extracted using the `extract_unquoted`
    method; otherwise, the `extract` method will be used.

    Input: anything
    Output: tuple of extracted selectors plus anything else in the input
    """
    use_unquote = adaptor_args.get('use_unquote', True) if adaptor_args else True

    if isinstance(location, XPathSelectorList):
        ret = location.extract()
    elif isinstance(location, XPathSelector):
        if location.xmlNode.type in ('text', 'cdata') and use_unquote:
            ret = location.extract_unquoted()
        else:
            ret = location.extract()
        ret = ret if hasattr(ret, '__iter__') else [ret]
    elif isinstance(location, list):
        ret = tuple(location)
    else:
        ret = tuple([location])

    return tuple(x for x in ret if x is not None)

class ExtractImageLinks(object):
    """
    This adaptor may receive either XPathSelectors pointing to
    the desired locations for finding image urls, or just a list of
    XPath expressions (which will be turned into selectors anyway).

    Input: XPathSelector, XPathSelectorList, iterable
    Output: tuple of urls (strings)
    """
    def __init__(self, response=None, canonicalize=True):
        self.response = response
        self.canonicalize = canonicalize

    def __call__(self, locations):
        if not locations:
            return tuple()
        elif not hasattr(locations, '__iter__'):
            locations = [locations]

        selectors, raw_links = [], []
        for location in locations:
            if isinstance(location, (XPathSelector, XPathSelectorList)):
                selectors.append(location)
            else:
                raw_links.append(location)

        if raw_links:
            base_url = get_base_url(self.response)
            raw_links = [urlparse.urljoin(base_url, unicode_to_str(rel_url)) for rel_url in raw_links]

        lx = HTMLImageLinkExtractor(locations=selectors, canonicalize=self.canonicalize)
        urls = map(lambda link: link.url, lx.extract_links(self.response))
        return tuple(urls + raw_links)

