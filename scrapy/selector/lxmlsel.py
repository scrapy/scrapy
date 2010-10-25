"""
XPath selectors based on lxml
"""

from lxml import etree

from scrapy.utils.python import flatten
from scrapy.utils.misc import extract_regex
from scrapy.utils.trackref import object_ref
from scrapy.utils.python import unicode_to_str
from scrapy.utils.decorator import deprecated
from scrapy.http import TextResponse

__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector', \
    'XPathSelectorList']

class XPathSelector(object_ref):

    __slots__ = ['response', 'text', 'expr', 'namespaces', '_root', '__weakref__']
    _parser = etree.HTMLParser
    _tostring_method = 'html'

    def __init__(self, response=None, text=None, root=None, expr=None, namespaces=None):
        if text:
            self.response = TextResponse(url='about:blank', \
                body=unicode_to_str(text, 'utf-8'), encoding='utf-8')
        else:
            self.response = response
        self._root = root
        self.namespaces = namespaces
        self.expr = expr

    @property
    def root(self):
        if self._root is None:
            parser = self._parser(encoding=self.response.encoding, recover=True)
            self._root = etree.fromstring(self.response.body, parser=parser, \
                base_url=self.response.url)
        return self._root

    def select(self, xpath):
        xpatheval = etree.XPathEvaluator(self.root, namespaces=self.namespaces)
        try:
            result = xpatheval(xpath)
        except etree.XPathError:
            raise ValueError("Invalid XPath: %s" % xpath)
        if hasattr(result, '__iter__'):
            result = [self.__class__(root=x, expr=xpath, namespaces=self.namespaces) \
                for x in result]
        elif result:
            result = [self.__class__(root=result, expr=xpath, namespaces=self.namespaces)]
        return XPathSelectorList(result)

    def re(self, regex):
        return extract_regex(regex, self.extract(), 'utf-8')

    def extract(self):
        try:
            return etree.tostring(self.root, method=self._tostring_method, \
                encoding=unicode).strip()
        except (AttributeError, TypeError):
            return unicode(self.root).strip()

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


class XPathSelectorList(list):

    def __getslice__(self, i, j):
        return XPathSelectorList(list.__getslice__(self, i, j))

    def select(self, xpath):
        return XPathSelectorList(flatten([x.select(xpath) for x in self]))

    def re(self, regex):
        return flatten([x.re(regex) for x in self])

    def extract(self):
        return [x.extract() if isinstance(x, XPathSelector) else x for x in self]

    @deprecated(use_instead='XPathSelectorList.extract_unquoted')
    def extract_unquoted(self):
        return [x.extract_unquoted() if isinstance(x, XPathSelector) else x for x in self]


class XmlXPathSelector(XPathSelector):
    """XPathSelector for XML content"""
    __slots__ = ()
    _parser = etree.XMLParser
    _tostring_method = 'xml'


class HtmlXPathSelector(XPathSelector):
    """XPathSelector for HTML content"""
    __slots__ = ()
    _parser = etree.HTMLParser
    _tostring_method = 'html'
