"""
XPath selectors based on lxml
"""

from lxml import etree

from scrapy.utils.misc import extract_regex
from scrapy.utils.trackref import object_ref
from scrapy.utils.python import unicode_to_str
from scrapy.utils.decorator import deprecated
from scrapy.http import TextResponse
from .list import XPathSelectorList

__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector', \
    'XPathSelectorList']

class XPathSelector(object_ref):

    __slots__ = ['response', 'text', 'expr', 'namespaces', '_root', '_xpathev', \
        '__weakref__']
    _parser = etree.HTMLParser
    _tostring_method = 'html'

    def __init__(self, response=None, text=None, root=None, expr=None, namespaces=None):
        if text:
            self.response = TextResponse(url='about:blank', \
                body=unicode_to_str(text, 'utf-8'), encoding='utf-8')
        else:
            self.response = response
        self._root = root
        self._xpathev = None
        self.namespaces = namespaces
        self.expr = expr

    @property
    def root(self):
        if self._root is None:
            url = self.response.url
            body = self.response.body_as_unicode().strip().encode('utf8') or '<html/>'
            parser = self._parser(recover=True, encoding='utf8')
            self._root = etree.fromstring(body, parser=parser, base_url=url)
            assert self._root is not None, 'BUG lxml selector with None root'
        return self._root

    def select(self, xpath):
        try:
            xpathev = self.root.xpath
        except AttributeError:
            return XPathSelectorList([])

        try:
            result = xpathev(xpath, namespaces=self.namespaces)
        except etree.XPathError:
            raise ValueError("Invalid XPath: %s" % xpath)

        if type(result) is not list:
            result = [result]

        result = [self.__class__(root=x, expr=xpath, namespaces=self.namespaces)
                  for x in result]
        return XPathSelectorList(result)

    def re(self, regex):
        return extract_regex(regex, self.extract())

    def extract(self):
        try:
            return etree.tostring(self.root, method=self._tostring_method, \
                encoding=unicode)
        except (AttributeError, TypeError):
            return unicode(self.root)

    def register_namespace(self, prefix, uri):
        if self.namespaces is None:
            self.namespaces = {}
        self.namespaces[prefix] = uri

    def __nonzero__(self):
        return bool(self.extract())

    def __str__(self):
        data = repr(self.extract()[:40])
        return "<%s xpath=%r data=%s>" % (type(self).__name__, self.expr, data)

    __repr__ = __str__


    @deprecated(use_instead='XPathSelector.extract')
    def extract_unquoted(self):
        return self.extract()


class XmlXPathSelector(XPathSelector):
    __slots__ = ()
    _parser = etree.XMLParser
    _tostring_method = 'xml'


class HtmlXPathSelector(XPathSelector):
    __slots__ = ()
    _parser = etree.HTMLParser
    _tostring_method = 'html'
