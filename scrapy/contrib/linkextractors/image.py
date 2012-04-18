"""
This module implements the HtmlImageLinkExtractor for extracting 
image links only.
"""

from urlparse import urljoin
from scrapy.link import Link
from scrapy.utils.url import canonicalize_url
from scrapy.utils.python import unicode_to_str, flatten
from scrapy.selector import XPathSelectorList, HtmlXPathSelector

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
        """Extract the links of all the images found in the selector given."""

        selectors = [selector] if selector.select("local-name()").re("^img$") \
                        else selector.select(".//img")

        def _img_attr(img, attr):
            """Helper to get the value of the given ``attr`` of the ``img``
            selector"""
            res = img.select("@%s" % attr).extract()
            return res[0] if res else None

        links = []
        for img in selectors:
            url = _img_attr(img, "src")
            text = _img_attr(img, "alt") or _img_attr(img, "title") or ""
            if not url:
                continue
            links.append(Link(unicode_to_str(url, encoding), text=text))
        return links


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
