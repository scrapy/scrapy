from urlparse import urlsplit, urlunsplit, urljoin

from scrapy.selector import HtmlXPathSelector as ScrapyHtmlXPathSelector
from scrapy.selector.list import XPathSelectorList as ScrapyXPathSelectorList


class XPathSelectorList(ScrapyXPathSelectorList):

    def extract_links(self, absolute=False):
        return [x.extract_links() for x in self]


class HtmlXPathSelector(ScrapyHtmlXPathSelector):

    _list_cls = XPathSelectorList

    def _get_base_url(self):
        if hasattr(self, '_base_url'):
            return self._base_url
        html_base = ''.join(self.select('//base/@href').extract())
        self._base_url = urljoin(self._root.base, html_base)
        return self._base_url

    def extract_links(self, absolute=False):
        """This finds any link in an action, archive, background, cite,
        classid, codebase, data, href, longdesc, profile, src, usemap, dynsrc,
        or lowsrc attribute.
        """
        xpath = '//@*['
        attrs = ('action', 'archive', 'background', 'cite', 'classid',
                'codebase', 'data', 'href', 'longdesc', 'profile', 'src',
                'usemap', 'dynsrc', 'lowsrc')
        xpath += ' or '.join('name()="{}"'.format(attr) for attr in attrs)
        xpath += ']'
        links = self.select(xpath).extract()
        if absolute:
            base = self._get_base_url()
            links = [urljoin(base, link)
                    for link in links]
        return [link.encode('utf-8') for link in links]
