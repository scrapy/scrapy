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


__all__ = ['Selector', 'SelectorList', 'XPath', 'CSS']

_ctgroup = {
    'html': {'_parser': etree.HTMLParser,
             '_csstranslator': ScrapyHTMLTranslator(),
             '_tostring_method': 'html'},
    'xml': {'_parser': etree.XMLParser,
            '_csstranslator': ScrapyGenericTranslator(),
            '_tostring_method': 'xml'},
}


def _st(response, st):
    if st is None:
        return 'xml' if isinstance(response, XmlResponse) else 'html'
    elif st in ('xml', 'html'):
        return st
    else:
        raise ValueError('Invalid type: %s' % st)


def _response_from_text(text, st):
    rt = XmlResponse if st == 'xml' else HtmlResponse
    return rt(url='about:blank', encoding='utf-8',
              body=unicode_to_str(text, 'utf-8'))


class XPath(object_ref):

    def __init__(self, xpath, type=None, namespaces=None):
        self.xpath = xpath
        self.namespaces = namespaces
        self._compiled_xpath = None

    def register_namespace(self, prefix, uri):
        if self.namespaces is None:
            self.namespaces = {}
        self.namespaces[prefix] = uri

    def __call__(self, document):
        if self._compiled_xpath is None:
            try:
                self._compiled_xpath = etree.XPath(self.xpath,
                    namespaces=self.namespaces)
            except etree.XPathError as e:
                raise ValueError("Invalid XPath: %s -- %s" % (self.xpath, str(e)))
        try:
            return self._compiled_xpath(document)
        except etree.XPathEvalError as e:
            raise ValueError("Invalid XPath: %s -- %s" % (self.xpath, str(e)))


class CSS(XPath):

    _csstranslator_type = 'html'

    def __init__(self, css, *args, **kwargs):
        self.css = css
        self._csstranslator = _ctgroup[self._csstranslator_type]['_csstranslator']
        super(CSS, self).__init__(
            self._csstranslator.css_to_xpath(css), *args, **kwargs)


class Selector(object_ref):

    __slots__ = ['response', 'text', 'namespaces', 'type', '_expr', '_root',
                 '__weakref__', '_parser', '_csstranslator', '_tostring_method']

    _default_type = None

    def __init__(self, response=None, text=None, type=None, namespaces=None,
                 _root=None, _expr=None):
        self.type = st = _st(response, type or self._default_type)
        self._parser = _ctgroup[st]['_parser']
        self._csstranslator = _ctgroup[st]['_csstranslator']
        self._tostring_method = _ctgroup[st]['_tostring_method']

        if text is not None:
            response = _response_from_text(text, st)

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

        if isinstance(query, (XPath, CSS)):
            result = query(self._root)
        else:
            try:
                result = xpathev(query, namespaces=self.namespaces)
            except etree.XPathError as e:
                raise ValueError("Invalid XPath: %s -- %s" % (query, str(e)))

        if type(result) is not list:
            result = [result]

        result = [self.__class__(_root=x, _expr=query,
                                 namespaces=self.namespaces,
                                 type=self.type)
                  for x in result]
        return SelectorList(result)

    def css(self, query):
        if isinstance(query, CSS):
            return self.xpath(query)
        else:
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

    def xpath(self, xpath):
        return self.__class__(flatten([x.xpath(xpath) for x in self]))

    def css(self, xpath):
        return self.__class__(flatten([x.css(xpath) for x in self]))

    def re(self, regex):
        return flatten([x.re(regex) for x in self])

    def extract(self):
        return [x.extract() for x in self]

    @deprecated(use_instead='.extract()')
    def extract_unquoted(self):
        return [x.extract_unquoted() for x in self]

    @deprecated(use_instead='.xpath()')
    def x(self, xpath):
        return self.select(xpath)

    @deprecated(use_instead='.xpath()')
    def select(self, xpath):
        return self.xpath(xpath)
