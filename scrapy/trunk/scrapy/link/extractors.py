"""
This module provides some LinkExtractors, which extend the base LinkExtractor
(scrapy.link.LinkExtractor) with some additional useful features.

See documentation in docs/ref/link-extractors.rst
"""

import re

from scrapy.link import LinkExtractor
from scrapy.utils.url import canonicalize_url, url_is_from_any_domain
from scrapy.xpath import HtmlXPathSelector
from scrapy.utils.misc import arg_to_iter

_re_type = type(re.compile("", 0))

_matches = lambda url, regexs: any((r.search(url) for r in regexs))
_is_valid_url = lambda url: url.split('://', 1)[0] in set(['http', 'https', 'file'])

class RegexLinkExtractor(LinkExtractor):

    def __init__(self, allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths=(), 
                 tags=('a', 'area'), attrs=('href'), canonicalize=True, unique=True, process_value=None):
        self.allow_res = [x if isinstance(x, _re_type) else re.compile(x) for x in arg_to_iter(allow)]
        self.deny_res = [x if isinstance(x, _re_type) else re.compile(x) for x in arg_to_iter(deny)]
        self.allow_domains = set(arg_to_iter(allow_domains))
        self.deny_domains = set(arg_to_iter(deny_domains))
        self.restrict_xpaths = tuple(arg_to_iter(restrict_xpaths))
        self.canonicalize = canonicalize
        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs
        LinkExtractor.__init__(self, tag=tag_func, attr=attr_func, 
            unique=unique, process_value=process_value)

    def extract_links(self, response):
        if self.restrict_xpaths:
            hxs = HtmlXPathSelector(response)
            html_slice = ''.join(''.join(html_fragm for html_fragm in hxs.x(xpath_expr).extract()) for xpath_expr in self.restrict_xpaths)
            links = self._extract_links(html_slice, response.url, response.encoding)
        else:
            links = LinkExtractor.extract_links(self, response)

        links = [link for link in links if _is_valid_url(link.url)]

        if self.allow_res:
            links = [link for link in links if _matches(link.url, self.allow_res)]
        if self.deny_res:
            links = [link for link in links if not _matches(link.url, self.deny_res)]
        if self.allow_domains:
            links = [link for link in links if url_is_from_any_domain(link.url, self.allow_domains)]
        if self.deny_domains:
            links = [link for link in links if not url_is_from_any_domain(link.url, self.deny_domains)]

        if self.canonicalize:
            for link in links:
                link.url = canonicalize_url(link.url)

        return links

    def matches(self, url):
        if self.allow_domains and not url_is_from_any_domain(url, self.allow_domains):
            return False
        if self.deny_domains and url_is_from_any_domain(url, self.deny_domains):
            return False

        allowed = [regex.search(url) for regex in self.allow_res] if self.allow_res else [True]
        denied = [regex.search(url) for regex in self.deny_res] if self.deny_res else []
        return any(allowed) and not any(denied)
