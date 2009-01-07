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

def extract(locations, use_unquote=True):
    """
    This adaptor tries to extract data from the given locations.
    Any XPathSelector in it will be extracted, and any other data
    will be added as-is to the result.

    If an XPathSelector is a text/cdata node, and `use_unquote`
    is True, that selector will be extracted using the `extract_unquoted`
    method; otherwise, the `extract` method will be used.

    Input: anything
    Output: list of extracted selectors plus anything else in the input
    """

    locations = flatten([locations])

    result = []
    for location in locations:
        if isinstance(location, XPathSelector):
            if location.xmlNode.type in ('text', 'cdata') and use_unquote:
                result.append(location.extract_unquoted())
            else:
                result.append(location.extract())
        else:
            result.append(location)
    return result

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
