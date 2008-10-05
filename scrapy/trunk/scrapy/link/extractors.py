"""
This module provides some LinkExtractors, which extend that base LinkExtractor
(scrapy.link.LinkExtractor) with some useful features.

"""

import re

from scrapy.link import LinkExtractor
from scrapy.utils.url import canonicalize_url, url_is_from_any_domain
from scrapy.utils.response import new_response_from_xpaths
from scrapy.utils.misc import dict_updatedefault

_re_type = type(re.compile("", 0))

_matches = lambda url, regexs: any((r.search(url) for r in regexs))
_is_valid_url = lambda url: url.split('://', 1)[0] in set(['http', 'https', 'file'])

class RegexLinkExtractor(LinkExtractor):
    """RegexLinkExtractor implements extends the base LinkExtractor by
    providing several mechanisms to extract the links.

    It's constructor parameters are:

    allow - list of regexes that the (absolute urls) must match to be extracted
    deny - ignore urls that match any of these regexes
    allow_domains - only extract urls from these domains
    deny_domains - ignore urls from these dmoains
    tags - look for urls in this tags
    attrs - look for urls in this attrs
    canonicalize - canonicalize all extracted urls using scrapy.utils.url.canonicalize_url

    Both 'allow' and 'deny' arguments can be a list of regexes strings or regex
    python objects (already compiled)

    Url matching is always performed against the absolute urls, never the
    relative urls found in pages.

    """
    
    def __init__(self, allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths=(), 
                 tags=('a', 'area'), attrs=('href'), canonicalize=True):
        self.allow_res = [x if isinstance(x, _re_type) else re.compile(x) for x in allow]
        self.deny_res = [x if isinstance(x, _re_type) else re.compile(x) for x in deny]
        self.allow_domains = set(allow_domains)
        self.deny_domains = set(deny_domains)
        self.restrict_xpaths = restrict_xpaths
        self.canonicalize = canonicalize
        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs
        LinkExtractor.__init__(self, tag=tag_func, attr=attr_func)

    def extract_urls(self, response):
        if self.restrict_xpaths:
            response = new_response_from_xpaths(response, self.restrict_xpaths)

        url_text = LinkExtractor.extract_urls(self, response)
        urls = [u for u in url_text.iterkeys() if _is_valid_url(u)]

        if self.allow_res:
            urls = [u for u in urls if _matches(u, self.allow_res)]
        if self.deny_res:
            urls = [u for u in urls if not _matches(u, self.deny_res)]
        if self.allow_domains:
            urls = [u for u in urls if url_is_from_any_domain(u, self.allow_domains)]
        if self.deny_domains:
            urls = [u for u in urls if not url_is_from_any_domain(u, self.deny_domains)]

        res = {}
        if self.canonicalize:
            for u in urls:
                res[canonicalize_url(u)] = url_text[u]
        else:
            for u in urls:
                res[u] = url_text[u]
        return res
