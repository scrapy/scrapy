"""
LinkExtractor provides en efficient way to extract links from pages

See documentation in docs/ref/link-extractors.rst
"""

from scrapy.utils.python import FixedSGMLParser, unique as unique_list, str_to_unicode
from scrapy.utils.url import safe_url_string, urljoin_rfc as urljoin

class LinkExtractor(FixedSGMLParser):

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
        base_url = self.base_url if self.base_url else response_url
        for link in links:
            link.url = urljoin(base_url, link.url)
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


class Link(object):
    """
    Link objects represent an extracted link by the LinkExtractor.
    At the moment, it contains just the url and link text.
    """

    __slots__ = 'url', 'text'

    def __init__(self, url, text=''):
        self.url = url
        self.text = text

    def __eq__(self, other):
        return self.url == other.url and self.text == other.text

    def __repr__(self):
        return '<Link url=%r text=%r >' % (self.url, self.text)
