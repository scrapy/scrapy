"""
Adaptors related with extraction of data
"""

import urlparse
import re
from scrapy import log
from scrapy.http import Response
from scrapy.utils.url import is_url
from scrapy.utils.python import flatten
from scrapy.xpath.selector import XPathSelector, XPathSelectorList

def _extract(locations, extractor='extract'):
    if isinstance(locations, (XPathSelector, XPathSelectorList)):
        return flatten(getattr(locations, extractor)())
    elif hasattr(locations, '__iter__'):
        return flatten([getattr(x, extractor)() if isinstance(x, (XPathSelector, XPathSelectorList)) else x for x in flatten(locations)])
    elif isinstance(locations, basestring):
        return [locations]
    else:
        return []

def extract(locations):
    """
    This adaptor extracts a list of strings
    from 'locations', which can be either an iterable,
    or an XPathSelector/XPathSelectorList.

    Input: XPathSelector, XPathSelectorList, iterable, basestring
    Output: list of unicodes
    """
    return _extract(locations)

def extract_unquoted(locations):
    """
    This adaptor extracts a list of unquoted strings
    from 'locations', which can be either an iterable,
    or an XPathSelector/XPathSelectorList.
    The difference between this and the extract adaptor is
    that this adaptor will only extract text nodes and unquote them.

    Input: XPathSelector, XPathSelectorList, iterable, basestring
    Output: list of unicodes
    """
    return _extract(locations, 'extract_unquoted')

class ExtractImages(object):
    """
    This adaptor may receive either an XPathSelector containing
    the desired locations for finding urls, a list of relative
    links to be resolved, or simply a link (relative or not).

    Input: XPathSelector, XPathSelectorList, iterable
    Output: list of unicodes
    """
    def __init__(self, response=None, base_url=None):
        BASETAG_RE = re.compile(r'<base\s+href\s*=\s*[\"\']\s*([^\"\'\s]+)\s*[\"\']', re.I)

        if response:
            match = BASETAG_RE.search(response.body.to_string()[0:4096])
            if match:
                self.base_url = match.group(1)
            else:
                self.base_url = response.url
        else:
            self.base_url = base_url

        if not self.base_url:
            log.msg('No base URL was found for ExtractImages adaptor, will only extract absolute URLs', log.WARNING)

    def extract_from_xpath(self, selector):
        ret = []
        if selector.xmlNode.type == 'element':
            if selector.xmlNode.name == 'a':
                children = selector.x('child::*')
                if len(children) > 1:
                    ret.extend(selector.x('.//@href'))
                    ret.extend(selector.x('.//@src'))
                elif len(children) == 1 and children[0].xmlNode.name == 'img':
                    ret.extend(children.x('@src'))
                else:
                    ret.extend(selector.x('@href'))
            elif selector.xmlNode.name == 'img':
                ret.extend(selector.x('@src'))
            elif selector.xmlNode.name == 'text':
                ret.extend(selector)
            else:
                ret.extend(selector.x('.//@href'))
                ret.extend(selector.x('.//@src'))
                ret.extend(selector.x('.//text()'))
        else:
            ret.append(selector)

        return ret

    def __call__(self, locations):
        if not locations:
            return []
        elif isinstance(locations, basestring):
            locations = [locations]

        rel_urls = []
        for location in flatten(locations):
            if isinstance(location, (XPathSelector, XPathSelectorList)):
                rel_urls.extend(self.extract_from_xpath(location))
            else:
                rel_urls.append(location)
        rel_urls = extract(rel_urls)

        if self.base_url:
            return [urlparse.urljoin(self.base_url, url) for url in rel_urls]
        else:
            return filter(rel_urls, is_url)
