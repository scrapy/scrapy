"""
XPath selectors based on lxml
"""

from lxml import etree
import six

from scrapy.utils.misc import extract_regex
from scrapy.utils.trackref import object_ref
from scrapy.utils.python import unicode_to_str, flatten, iflatten
from scrapy.utils.decorators import deprecated
from scrapy.http import HtmlResponse, XmlResponse
from .lxmldocument import LxmlDocument
from .csstranslator import ScrapyHTMLTranslator, ScrapyGenericTranslator


__all__ = ['Selector', 'SelectorList']


class SafeXMLParser(etree.XMLParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('resolve_entities', False)
        super(SafeXMLParser, self).__init__(*args, **kwargs)

_ctgroup = {
    'html': {'_parser': etree.HTMLParser,
             '_csstranslator': ScrapyHTMLTranslator(),
             '_tostring_method': 'html'},
    'xml': {'_parser': SafeXMLParser,
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


class Selector(object_ref):

    __slots__ = ['response', 'text', 'namespaces', 'type', '_expr', '_root',
                 '__weakref__', '_parser', '_csstranslator', '_tostring_method']

    _default_type = None
    _default_namespaces = {
        "re": "http://exslt.org/regular-expressions",

        # supported in libxslt:
        # set:difference
        # set:has-same-node
        # set:intersection
        # set:leading
        # set:trailing
        "set": "http://exslt.org/sets"
    }
    _lxml_smart_strings = False

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
        self.namespaces = dict(self._default_namespaces)
        if namespaces is not None:
            self.namespaces.update(namespaces)
        self._root = _root
        self._expr = _expr

    def xpath(self, query):
        try:
            xpathev = self._root.xpath
        except AttributeError:
            return SelectorList([])

        try:
            result = xpathev(query, namespaces=self.namespaces,
                             smart_strings=self._lxml_smart_strings)
        except etree.XPathError:
            msg = u"Invalid XPath: %s" % query
            raise ValueError(msg if six.PY3 else msg.encode("unicode_escape"))

        if type(result) is not list:
            result = [result]

        result = [self.__class__(_root=x, _expr=query,
                                 namespaces=self.namespaces,
                                 type=self.type)
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

    def xpath(self, xpath):
        return self.__class__(flatten([x.xpath(xpath) for x in self]))

    def css(self, xpath):
        return self.__class__(flatten([x.css(xpath) for x in self]))

    def re(self, regex):
        return flatten([x.re(regex) for x in self])

    def re_first(self, regex):
        for el in iflatten(x.re(regex) for x in self):
            return el

    def extract(self):
        return [x.extract() for x in self]

    def extract_first(self, default=None):
        for x in self:
            return x.extract()
        else:
            return default

    @deprecated(use_instead='.extract()')
    def extract_unquoted(self):
        return [x.extract_unquoted() for x in self]

    @deprecated(use_instead='.xpath()')
    def x(self, xpath):
        return self.select(xpath)

    @deprecated(use_instead='.xpath()')
    def select(self, xpath):
        return self.xpath(xpath)
