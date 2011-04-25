"""Request Extractors"""
from w3lib.url import safe_url_string, urljoin_rfc

from scrapy.http import Request
from scrapy.selector import HtmlXPathSelector
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import FixedSGMLParser, str_to_unicode

from itertools import ifilter


class BaseSgmlRequestExtractor(FixedSGMLParser):
    """Base SGML Request Extractor"""

    def __init__(self, tag='a', attr='href'):
        """Initialize attributes"""
        FixedSGMLParser.__init__(self)

        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
        self.current_request = None

    def extract_requests(self, response):
        """Returns list of requests extracted from response"""
        return self._extract_requests(response.body, response.url,
                                  response.encoding)

    def _extract_requests(self, response_text, response_url, response_encoding):
        """Extract requests with absolute urls"""
        self.reset()
        self.feed(response_text)
        self.close()

        base_url = urljoin_rfc(response_url, self.base_url) if self.base_url else response_url
        self._make_absolute_urls(base_url, response_encoding)
        self._fix_link_text_encoding(response_encoding)

        return self.requests

    def _make_absolute_urls(self, base_url, encoding):
        """Makes all request's urls absolute"""
        self.requests = [x.replace(url=safe_url_string(urljoin_rfc(base_url, \
            x.url, encoding), encoding)) for x in self.requests]

    def _fix_link_text_encoding(self, encoding):
        """Convert link_text to unicode for each request"""
        for req in self.requests:
            req.meta.setdefault('link_text', '')
            req.meta['link_text'] = str_to_unicode(req.meta['link_text'],
                                                   encoding) 

    def reset(self):
        """Reset state"""
        FixedSGMLParser.reset(self)
        self.requests = []
        self.base_url = None
            
    def unknown_starttag(self, tag, attrs):
        """Process unknown start tag"""
        if 'base' == tag:
            self.base_url = dict(attrs).get('href')

        _matches = lambda (attr, value): self.scan_attr(attr) \
                                        and value is not None
        if self.scan_tag(tag):
            for attr, value in ifilter(_matches, attrs):
                req = Request(url=value)
                self.requests.append(req)
                self.current_request = req

    def unknown_endtag(self, tag):
        """Process unknown end tag"""
        self.current_request = None

    def handle_data(self, data):
        """Process data"""
        current = self.current_request
        if current and not 'link_text' in current.meta:
            current.meta['link_text'] = data.strip()


class SgmlRequestExtractor(BaseSgmlRequestExtractor):
    """SGML Request Extractor"""

    def __init__(self, tags=None, attrs=None):
        """Initialize with custom tag & attribute function checkers"""
        # defaults
        tags = tuple(tags) if tags else ('a', 'area')
        attrs = tuple(attrs) if attrs else ('href', )

        tag_func = lambda x: x in tags
        attr_func = lambda x: x in attrs
        BaseSgmlRequestExtractor.__init__(self, tag=tag_func, attr=attr_func)

# TODO: move to own file
class XPathRequestExtractor(SgmlRequestExtractor):
    """SGML Request Extractor with XPath restriction"""

    def __init__(self, restrict_xpaths, tags=None, attrs=None):
        """Initialize XPath restrictions"""
        self.restrict_xpaths = tuple(arg_to_iter(restrict_xpaths))
        SgmlRequestExtractor.__init__(self, tags, attrs)

    def extract_requests(self, response):
        """Restrict to XPath regions"""
        hxs = HtmlXPathSelector(response)
        fragments = (''.join(
                            html_frag for html_frag in hxs.select(xpath).extract()
                        ) for xpath in self.restrict_xpaths)
        html_slice = ''.join(html_frag for html_frag in fragments)
        return self._extract_requests(html_slice, response.url,
                                        response.encoding)

