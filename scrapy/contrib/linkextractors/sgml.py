"""
SGMLParser-based Link extractors
"""
import re
from urlparse import urlparse, urljoin
from w3lib.url import safe_url_string
from scrapy.selector import Selector
from scrapy.link import Link
from scrapy.linkextractor import FilteringLinkExtractor
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import FixedSGMLParser, unique as unique_list, str_to_unicode
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
            link.text = str_to_unicode(link.text, response_encoding, errors='replace').strip()
            ret.append(link)

        return ret

    def _process_links(self, links):
        """ Normalize and filter extracted links

        The subclass should override it if necessary
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
                        link = Link(url=url, nofollow=True if dict(attrs).get('rel') == 'nofollow' else False)
                        self.links.append(link)
                        self.current_link = link

    def unknown_endtag(self, tag):
        if self.scan_tag(tag):
            self.current_link = None

    def handle_data(self, data):
        if self.current_link:
            self.current_link.text = self.current_link.text + data

    def matches(self, url):
        """This extractor matches with any url, since
        it doesn't contain any patterns"""
        return True


class SgmlLinkExtractor(FilteringLinkExtractor):

    def __init__(self, allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths=(),
                 tags=('a', 'area'), attrs=('href',), canonicalize=True, unique=True, process_value=None,
                 deny_extensions=None):
        tags, attrs = set(arg_to_iter(tags)), set(arg_to_iter(attrs))
        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs
        lx = BaseSgmlLinkExtractor(tag=tag_func, attr=attr_func,
            unique=unique, process_value=process_value)
        super(SgmlLinkExtractor, self).__init__(lx, allow, deny,
            allow_domains, deny_domains, restrict_xpaths, canonicalize,
            deny_extensions)

        # FIXME: was added to fix a RegexLinkExtractor testcase
        self.base_url = None

    def extract_links(self, response):
        base_url = None
        if self.restrict_xpaths:
            sel = Selector(response)
            base_url = get_base_url(response)
            body = u''.join(f
                            for x in self.restrict_xpaths
                            for f in sel.xpath(x).extract()
                            ).encode(response.encoding, errors='xmlcharrefreplace')
        else:
            body = response.body

        links = self._extract_links(body, response.url, response.encoding, base_url)
        links = self._process_links(links)
        return links
