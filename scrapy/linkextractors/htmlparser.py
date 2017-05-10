"""
HTMLParser-based link extractor
"""
import warnings
import six
from six.moves.html_parser import HTMLParser
from six.moves.urllib.parse import urljoin

from w3lib.url import safe_url_string
from w3lib.html import strip_html5_whitespace

from scrapy.link import Link
from scrapy.utils.python import unique as unique_list
from scrapy.exceptions import ScrapyDeprecationWarning


class HtmlParserLinkExtractor(HTMLParser):

    def __init__(self, tag="a", attr="href", process=None, unique=False,
                 strip=True):
        HTMLParser.__init__(self)

        warnings.warn(
            "HtmlParserLinkExtractor is deprecated and will be removed in "
            "future releases. Please use scrapy.linkextractors.LinkExtractor",
            ScrapyDeprecationWarning, stacklevel=2,
        )

        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
        self.process_attr = process if callable(process) else lambda v: v
        self.unique = unique
        self.strip = strip

    def _extract_links(self, response_text, response_url, response_encoding):
        self.reset()
        self.feed(response_text)
        self.close()

        links = unique_list(self.links, key=lambda link: link.url) if self.unique else self.links

        ret = []
        base_url = urljoin(response_url, self.base_url) if self.base_url else response_url
        for link in links:
            if isinstance(link.url, six.text_type):
                link.url = link.url.encode(response_encoding)
            try:
                link.url = urljoin(base_url, link.url)
            except ValueError:
                continue
            link.url = safe_url_string(link.url, response_encoding)
            link.text = link.text.decode(response_encoding)
            ret.append(link)

        return ret

    def extract_links(self, response):
        # wrapper needed to allow to work directly with text
        return self._extract_links(response.body, response.url, response.encoding)

    def reset(self):
        HTMLParser.reset(self)

        self.base_url = None
        self.current_link = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'base':
            self.base_url = dict(attrs).get('href')
        if self.scan_tag(tag):
            for attr, value in attrs:
                if self.scan_attr(attr):
                    if self.strip:
                        value = strip_html5_whitespace(value)
                    url = self.process_attr(value)
                    link = Link(url=url)
                    self.links.append(link)
                    self.current_link = link

    def handle_endtag(self, tag):
        if self.scan_tag(tag):
            self.current_link = None

    def handle_data(self, data):
        if self.current_link:
            self.current_link.text = self.current_link.text + data

    def matches(self, url):
        """This extractor matches with any url, since
        it doesn't contain any patterns"""
        return True
