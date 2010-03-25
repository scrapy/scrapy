"""
lxml-based link extractors (experimental)

NOTE: The ideal name for this module would be `lxml`, but that's not possible
because it collides with the lxml library module.
"""

from lxml import etree
import lxml.html

from scrapy.link import Link
from scrapy.utils.python import unique as unique_list, str_to_unicode
from scrapy.utils.url import safe_url_string, urljoin_rfc

class LxmlLinkExtractor(object):
    def __init__(self, tag="a", attr="href", process=None, unique=False):
        scan_tag = tag if callable(tag) else lambda t: t == tag
        scan_attr = attr if callable(attr) else lambda a: a == attr
        process_attr = process if callable(process) else lambda v: v

        self.unique = unique

        target = LinkTarget(scan_tag, scan_attr, process_attr)
        self.parser = etree.HTMLParser(target=target)

    def _extract_links(self, response_text, response_url, response_encoding):
        self.base_url, self.links = etree.HTML(response_text, self.parser) 

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
        return self._extract_links(response.body, response.url, 
                                   response.encoding)

    def matches(self, url):
        """This extractor matches with any url, since it doesn't contain any patterns"""
        return True


class LinkTarget(object):
    def __init__(self, scan_tag, scan_attr, process_attr):
        self.scan_tag = scan_tag
        self.scan_attr = scan_attr
        self.process_attr = process_attr

        self.base_url = None
        self.links = []

        self.current_link = None

    def start(self, tag, attrs):
        if tag == 'base':
            self.base_url = dict(attrs).get('href')
        if self.scan_tag(tag):
            for attr, value in attrs.iteritems():
                if self.scan_attr(attr):
                    url = self.process_attr(value)
                    link = Link(url=url)
                    self.links.append(link)
                    self.current_link = link

    def end(self, tag):
        self.current_link = None

    def data(self, data):
        if self.current_link and not self.current_link.text:
            self.current_link.text = data.strip()

    def close(self):
        return self.base_url, self.links


class LxmlParserLinkExtractor(object):
    def __init__(self, tag="a", attr="href", process=None, unique=False):
        self.scan_tag = tag if callable(tag) else lambda t: t == tag
        self.scan_attr = attr if callable(attr) else lambda a: a == attr
        self.process_attr = process if callable(process) else lambda v: v
        self.unique = unique

        self.links = []

    def _extract_links(self, response_text, response_url):
        html = lxml.html.fromstring(response_text)
        html.make_links_absolute(response_url)
        for e, a, l, p in html.iterlinks():
            if self.scan_tag(e.tag):
                if self.scan_attr(a):
                    link = Link(self.process_attr(l), text=e.text)
                    self.links.append(link)

        links = unique_list(self.links, key=lambda link: link.url) \
                if self.unique else self.links

        return links

    def extract_links(self, response):
        # wrapper needed to allow to work directly with text
        return self._extract_links(response.body, response.url)


