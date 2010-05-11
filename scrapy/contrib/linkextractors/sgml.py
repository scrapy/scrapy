"""
SGMLParser-based Link extractors
"""

import re

from scrapy.selector import HtmlXPathSelector
from scrapy.link import Link
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import FixedSGMLParser, unique as unique_list, str_to_unicode
from scrapy.utils.url import safe_url_string, urljoin_rfc, canonicalize_url, url_is_from_any_domain

class BaseSgmlLinkExtractor(FixedSGMLParser):

    def __init__(self, tag="a", attr="href", unique=False, process_value=None):
        FixedSGMLParser.__init__(self)
        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
        self.process_value = (lambda v: v) if process_value is None else process_value
        self.current_link = None
        self.unique = unique

    def _extract_links(self, response_text, response_url, response_encoding):
        self.reset()
        self.feed(response_text)
        self.close()

        links = unique_list(self.links, key=lambda link: link.url) if self.unique else self.links

        ret = []
        base_url = urljoin_rfc(response_url, self.base_url) if self.base_url else response_url
        for link in links:
            link.url = urljoin_rfc(base_url, link.url, response_encoding)
            link.url = safe_url_string(link.url, response_encoding)
            link.text = str_to_unicode(link.text, response_encoding)
            ret.append(link)

        return ret

    def extract_links(self, response):
        # wrapper needed to allow to work directly with text
        return self._extract_links(response.body, response.url, response.encoding)

    def reset(self):
        FixedSGMLParser.reset(self)
        self.links = []
        self.base_url = None

    def unknown_starttag(self, tag, attrs):
        if tag == 'base':
            self.base_url = dict(attrs).get('href')
        if self.scan_tag(tag):
            for attr, value in attrs:
                if self.scan_attr(attr):
                    url = self.process_value(value)
                    if url is not None:
                        link = Link(url=url)
                        self.links.append(link)
                        self.current_link = link

    def unknown_endtag(self, tag):
        self.current_link = None

    def handle_data(self, data):
        if self.current_link and not self.current_link.text:
            self.current_link.text = data.strip()

    def matches(self, url):
        """This extractor matches with any url, since
        it doesn't contain any patterns"""
        return True

_re_type = type(re.compile("", 0))

_matches = lambda url, regexs: any((r.search(url) for r in regexs))
_is_valid_url = lambda url: url.split('://', 1)[0] in set(['http', 'https', 'file'])

class SgmlLinkExtractor(BaseSgmlLinkExtractor):

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
        BaseSgmlLinkExtractor.__init__(self, tag=tag_func, attr=attr_func, 
            unique=unique, process_value=process_value)

    def extract_links(self, response):
        if self.restrict_xpaths:
            hxs = HtmlXPathSelector(response)
            html_slice = ''.join(''.join(html_fragm for html_fragm in hxs.select(xpath_expr).extract()) \
                for xpath_expr in self.restrict_xpaths)
            links = self._extract_links(html_slice, response.url, response.encoding)
        else:
            links = BaseSgmlLinkExtractor.extract_links(self, response)

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
