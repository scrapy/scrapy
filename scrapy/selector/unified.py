"""
XPath selectors based on lxml
"""

from lxml import etree

from scrapy.utils.misc import extract_regex
from scrapy.utils.trackref import object_ref
from scrapy.utils.python import unicode_to_str, flatten
from scrapy.utils.decorator import deprecated
from scrapy.http import HtmlResponse, XmlResponse
from .lxmldocument import LxmlDocument
from .csstranslator import ScrapyHTMLTranslator, ScrapyGenericTranslator


__all__ = ['Selector', 'SelectorList']

_ctgroup = {
    'html': {'_parser': etree.HTMLParser,
             '_csstranslator': ScrapyHTMLTranslator(),
             '_tostring_method': 'html'},
    'xml': {'_parser': etree.XMLParser,
            '_csstranslator': ScrapyGenericTranslator(),
            '_tostring_method': 'xml'},
}


def _ct(response, ct):
    if ct is None:
        return 'xml' if isinstance(response, XmlResponse) else 'html'
    elif ct in ('xml', 'html'):
        return ct
    else:
        raise ValueError('Invalid contenttype: %s' % ct)


def _response_from_text(text, ct):
    rt = XmlResponse if ct == 'xml' else HtmlResponse
    return rt(url='about:blank', encoding='utf-8',
              body=unicode_to_str(text, 'utf-8'))


class Selector(object_ref):

    __slots__ = ['response', 'text', 'namespaces', 'contenttype', '_expr', '_root',
                 '__weakref__', '_parser', '_csstranslator', '_tostring_method']

    default_contenttype = None

    def __init__(self, response=None, text=None, namespaces=None, contenttype=None,
                 _root=None, _expr=None):

        self.contenttype = ct = self.default_contenttype or _ct(contenttype)
        self._parser = _ctgroup[ct]['_parser']
        self._csstranslator = _ctgroup[ct]['_csstranslator']
        self._tostring_method = _ctgroup[ct]['_tostring_method']

        if text is not None:
            response = _response_from_text(text, ct)

        if response is not None:
            _root = LxmlDocument(response, self._parser)

        self.response = response
        self.namespaces = namespaces
        self._root = _root
        self._expr = _expr

    def xpath(self, query):
        try:
            xpathev = self._root.xpath
        except AttributeError:
            return SelectorList([])

        try:
            result = xpathev(query, namespaces=self.namespaces)
        except etree.XPathError:
            raise ValueError("Invalid XPath: %s" % query)

        if type(result) is not list:
            result = [result]

        result = [self.__class__(_root=x, _expr=query,
                                 namespaces=self.namespaces,
                                 contenttype=self.contenttype)
                  for x in result]
        return SelectorList(result)

    def css(self, query):
        return self.xpath(self._css2xpath(query))

    def _css2xpath(self, query):
        return self._csstranslator.css_to_xpath(query)

    def re(self, regex):
        return extract_regex(regex, self.extract())

    def extract(self):
        try:
            return etree.tostring(self._root,
                                  method=self._tostring_method,
                                  encoding=unicode,
                                  with_tail=False)
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

    def remove_namespaces(self):
        for el in self._root.iter('*'):
            if el.tag.startswith('{'):
                el.tag = el.tag.split('}', 1)[1]
            # loop on element attributes also
            for an in el.attrib.keys():
                if an.startswith('{'):
                    el.attrib[an.split('}', 1)[1]] = el.attrib.pop(an)

    def __nonzero__(self):
        return bool(self.extract())

    def __str__(self):
        data = repr(self.extract()[:40])
        return "<%s xpath=%r data=%s>" % (type(self).__name__, self._expr, data)
    __repr__ = __str__

    # Deprecated api
    @deprecated(use_instead='.xpath()')
    def select(self, xpath):
        return self.xpath(xpath)

    @deprecated(use_instead='.extract()')
    def extract_unquoted(self):
        return self.extract()


class SelectorList(list):

    def __getslice__(self, i, j):
        return self.__class__(list.__getslice__(self, i, j))

    def select(self, xpath):
        return self.__class__(flatten([x.select(xpath) for x in self]))

    def re(self, regex):
        return flatten([x.re(regex) for x in self])

    def extract(self):
        return [x.extract() for x in self]

    @deprecated(use_instead='SelectorList.extract')
    def extract_unquoted(self):
        return [x.extract_unquoted() for x in self]

    @deprecated(use_instead='SelectorList.select')
    def x(self, xpath):
        return self.select(xpath)
