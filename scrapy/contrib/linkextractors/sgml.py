"""
SGMLParser-based Link extractors
"""

import re
from urlparse import urlparse, urljoin

from w3lib.url import safe_url_string

from scrapy.selector import HtmlXPathSelector
from scrapy.link import Link
from scrapy.linkextractor import IGNORED_EXTENSIONS
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import FixedSGMLParser, unique as unique_list, str_to_unicode
from scrapy.utils.url import canonicalize_url, url_is_from_any_domain, url_has_any_extension
from scrapy.utils.response import get_base_url

class BaseSgmlLinkExtractor(FixedSGMLParser):

    def __init__(self, tag="a", attr="href", unique=False, process_value=None):
        FixedSGMLParser.__init__(self)
        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
        self.process_value = (lambda v: v) if process_value is None else process_value
        self.current_link = None
        self.unique = unique

    def _extract_links(self, response_text, response_url, response_encoding, base_url=None):
        """ Do the real extraction work """
        self.reset()
        self.feed(response_text)
        self.close()

        ret = []
        if base_url is None:
            base_url = urljoin(response_url, self.base_url) if self.base_url else response_url
        for link in self.links:
            if isinstance(link.url, unicode):
                link.url = link.url.encode(response_encoding)
            link.url = urljoin(base_url, link.url)
            link.url = safe_url_string(link.url, response_encoding)
            link.text = str_to_unicode(link.text, response_encoding, errors='replace')
            ret.append(link)

        return ret

    def _process_links(self, links):
        """ Normalize and filter extracted links

        The subclass should override it if neccessary
        """
        links = unique_list(links, key=lambda link: link.url) if self.unique else links
        return links

    def extract_links(self, response):
        # wrapper needed to allow to work directly with text
        links = self._extract_links(response.body, response.url, response.encoding)
        links = self._process_links(links)
        return links

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
        if self.current_link:
            self.current_link.text = self.current_link.text + data.strip()

    def matches(self, url):
        """This extractor matches with any url, since
        it doesn't contain any patterns"""
        return True

_re_type = type(re.compile("", 0))

_matches = lambda url, regexs: any((r.search(url) for r in regexs))
_is_valid_url = lambda url: url.split('://', 1)[0] in set(['http', 'https', 'file'])

class SgmlLinkExtractor(BaseSgmlLinkExtractor):

    def __init__(self, allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths=(), 
                 tags=('a', 'area'), attrs=('href'), canonicalize=True, unique=True, process_value=None,
                 deny_extensions=None):
        self.allow_res = [x if isinstance(x, _re_type) else re.compile(x) for x in arg_to_iter(allow)]
        self.deny_res = [x if isinstance(x, _re_type) else re.compile(x) for x in arg_to_iter(deny)]
        self.allow_domains = set(arg_to_iter(allow_domains))
        self.deny_domains = set(arg_to_iter(deny_domains))
        self.restrict_xpaths = tuple(arg_to_iter(restrict_xpaths))
        self.canonicalize = canonicalize
        if deny_extensions is None:
            deny_extensions = IGNORED_EXTENSIONS
        self.deny_extensions = set(['.' + e for e in deny_extensions])
        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs
        BaseSgmlLinkExtractor.__init__(self, tag=tag_func, attr=attr_func, 
            unique=unique, process_value=process_value)

    def extract_links(self, response):
        base_url = None
        if self.restrict_xpaths:
            hxs = HtmlXPathSelector(response)
            html = ''.join(''.join(html_fragm for html_fragm in hxs.select(xpath_expr).extract()) \
                for xpath_expr in self.restrict_xpaths)
            base_url = get_base_url(response)
        else:
            html = response.body

        links = self._extract_links(html, response.url, response.encoding, base_url)
        links = self._process_links(links)
        return links

    def _process_links(self, links):
        links = [x for x in links if self._link_allowed(x)]
        links = BaseSgmlLinkExtractor._process_links(self, links)
        return links

    def _link_allowed(self, link):
        parsed_url = urlparse(link.url)
        allowed = _is_valid_url(link.url)
        if self.allow_res:
            allowed &= _matches(link.url, self.allow_res)
        if self.deny_res:
            allowed &= not _matches(link.url, self.deny_res)
        if self.allow_domains:
            allowed &= url_is_from_any_domain(parsed_url, self.allow_domains)
        if self.deny_domains:
            allowed &= not url_is_from_any_domain(parsed_url, self.deny_domains)
        if self.deny_extensions:
            allowed &= not url_has_any_extension(parsed_url, self.deny_extensions)
        if allowed and self.canonicalize:
            link.url = canonicalize_url(parsed_url)
        return allowed

    def matches(self, url):
        if self.allow_domains and not url_is_from_any_domain(url, self.allow_domains):
            return False
        if self.deny_domains and url_is_from_any_domain(url, self.deny_domains):
            return False

        allowed = [regex.search(url) for regex in self.allow_res] if self.allow_res else [True]
        denied = [regex.search(url) for regex in self.deny_res] if self.deny_res else []
        return any(allowed) and not any(denied)
