"""
XPath selectors based on lxml
"""

from lxml import etree

from scrapy.utils.misc import extract_regex
from scrapy.utils.trackref import object_ref
from scrapy.utils.python import unicode_to_str
from scrapy.utils.decorator import deprecated
from scrapy.http import TextResponse
from .lxmldocument import LxmlDocument
from .list import XPathSelectorList


__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector', \
           'XPathSelectorList']


class XPathSelector(object_ref):

    __slots__ = ['response', 'text', 'namespaces', '_expr', '_root', '__weakref__']
    _parser = etree.HTMLParser
    _tostring_method = 'html'

    def __init__(self, response=None, text=None, namespaces=None, _root=None, _expr=None):
        if text is not None:
            response = TextResponse(url='about:blank', \
                body=unicode_to_str(text, 'utf-8'), encoding='utf-8')
        if response is not None:
            _root = LxmlDocument(response, self._parser)

        self.namespaces = namespaces
        self.response = response
        self._root = _root
        self._expr = _expr

    def select(self, xpath):
        try:
            xpathev = self._root.xpath
        except AttributeError:
            return XPathSelectorList([])

        try:
            result = xpathev(xpath, namespaces=self.namespaces)
        except etree.XPathError:
            raise ValueError("Invalid XPath: %s" % xpath)

        if type(result) is not list:
            result = [result]

        result = [self.__class__(_root=x, _expr=xpath, namespaces=self.namespaces)
                  for x in result]
        return XPathSelectorList(result)

    def re(self, regex):
        return extract_regex(regex, self.extract())

    def extract(self):
        try:
            return etree.tostring(self._root, method=self._tostring_method, \
                encoding=unicode, with_tail=False)
        except (AttributeError, TypeError):
            if self._root is True:
                return u'1'
            elif self._root is False:
                return u'0'
            else:
                return unicode(self._root)

    def register_namespace(self, prefix, uri):
        if self.namespaces is None:
            self.namespaces = {}
        self.namespaces[prefix] = uri

    def __nonzero__(self):
        return bool(self.extract())

    def __str__(self):
        data = repr(self.extract()[:40])
        return "<%s xpath=%r data=%s>" % (type(self).__name__, self._expr, data)

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
