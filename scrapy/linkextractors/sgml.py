"""
SGMLParser-based Link extractors
"""
from six.moves.urllib.parse import urljoin
import warnings
from sgmllib import SGMLParser

from w3lib.url import safe_url_string
from scrapy.selector import Selector
from scrapy.link import Link
from scrapy.linkextractors import FilteringLinkExtractor
from scrapy.utils.misc import arg_to_iter, rel_has_nofollow
from scrapy.utils.python import unique as unique_list, to_unicode
from scrapy.utils.response import get_base_url
from scrapy.exceptions import ScrapyDeprecationWarning


class BaseSgmlLinkExtractor(SGMLParser):

    def __init__(self, tag="a", attr="href", unique=False, process_value=None):
        warnings.warn(
            "BaseSgmlLinkExtractor is deprecated and will be removed in future releases. "
            "Please use scrapy.linkextractors.LinkExtractor",
            ScrapyDeprecationWarning, stacklevel=2,
        )
        SGMLParser.__init__(self)
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
            try:
                link.url = urljoin(base_url, link.url)
            except ValueError:
                continue
            link.url = safe_url_string(link.url, response_encoding)
            link.text = to_unicode(link.text, response_encoding, errors='replace').strip()
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
        SGMLParser.reset(self)
        self.links = []
        self.base_url = None
        self.current_link = None

    def unknown_starttag(self, tag, attrs):
        if tag == 'base':
            self.base_url = dict(attrs).get('href')
        if self.scan_tag(tag):
            for attr, value in attrs:
                if self.scan_attr(attr):
                    url = self.process_value(value)
                    if url is not None:
                        link = Link(url=url, nofollow=rel_has_nofollow(dict(attrs).get('rel')))
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
                 tags=('a', 'area'), attrs=('href',), canonicalize=True, unique=True,
                 process_value=None, deny_extensions=None, restrict_css=()):

        warnings.warn(
            "SgmlLinkExtractor is deprecated and will be removed in future releases. "
            "Please use scrapy.linkextractors.LinkExtractor",
            ScrapyDeprecationWarning, stacklevel=2,
        )

        tags, attrs = set(arg_to_iter(tags)), set(arg_to_iter(attrs))
        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', ScrapyDeprecationWarning)
            lx = BaseSgmlLinkExtractor(tag=tag_func, attr=attr_func,
                unique=unique, process_value=process_value)

        super(SgmlLinkExtractor, self).__init__(lx, allow=allow, deny=deny,
            allow_domains=allow_domains, deny_domains=deny_domains,
            restrict_xpaths=restrict_xpaths, restrict_css=restrict_css,
            canonicalize=canonicalize, deny_extensions=deny_extensions)

    def extract_links(self, response):
        base_url = None
        if self.restrict_xpaths:
            base_url = get_base_url(response)
            body = u''.join(f
                            for x in self.restrict_xpaths
                            for f in response.xpath(x).extract()
                            ).encode(response.encoding, errors='xmlcharrefreplace')
        else:
            body = response.body

        links = self._extract_links(body, response.url, response.encoding, base_url)
        links = self._process_links(links)
        return links
