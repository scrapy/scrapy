"""
LinkExtractor provides en efficient way to extract links from pages

See documentation in docs/ref/link-extractors.rst
"""

from scrapy.utils.python import FixedSGMLParser, unique as unique_list, str_to_unicode
from scrapy.utils.url import safe_url_string, urljoin_rfc as urljoin

class LinkExtractor(FixedSGMLParser):
    """LinkExtractor are used to extract links from web pages. They are
    instantiated and later "applied" to a Response using the extract_links
    method which must receive a Response object and return a list of Link objects
    containing the (absolute) urls to follow, and the links texts.

    This is the base LinkExtractor class that provides enough basic
    functionality for extracting links to follow, but you could override this
    class or create a new one if you need some additional functionality. The
    only requisite is that the new (or overrided) class must provide a
    extract_links method that receives a Response and returns a list of Link objects.

    This LinkExtractor always returns percent-encoded URLs, using the detected encoding
    from the response.

    The constructor arguments are:

    * tag (string or function)
      * a tag name which is used to search for links (defaults to "a")
      * a function which receives a tag name and returns whether to scan it
    * attr (string or function)
      * an attribute name which is used to search for links (defaults to "href")
      * a function which receives an attribute name and returns whether to scan it
    * unique - if True the same urls won't be extracted twice, otherwise the
      same urls will be extracted multiple times (with potentially different link texts)
    """

    def __init__(self, tag="a", attr="href", unique=False):
        FixedSGMLParser.__init__(self)
        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
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
                    link = Link(url=value)
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
