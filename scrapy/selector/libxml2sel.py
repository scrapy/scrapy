"""
XPath selectors based on libxml2
"""

import libxml2

from scrapy.http import TextResponse
from scrapy.utils.python import unicode_to_str
from scrapy.utils.misc import extract_regex
from scrapy.utils.trackref import object_ref
from scrapy.utils.decorator import deprecated
from .factories import xmlDoc_from_html, xmlDoc_from_xml
from .document import Libxml2Document
from .list import XPathSelectorList

__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector', \
    'XPathSelectorList']

class XPathSelector(object_ref):

    __slots__ = ['doc', 'xmlNode', 'expr', '__weakref__']

    def __init__(self, response=None, text=None, node=None, parent=None, expr=None):
        if parent:
            self.doc = parent.doc
            self.xmlNode = node
        elif response:
            self.doc = Libxml2Document(response, factory=self._get_libxml2_doc)
            self.xmlNode = self.doc.xmlDoc
        elif text:
            response = TextResponse(url='about:blank', \
                body=unicode_to_str(text, 'utf-8'), encoding='utf-8')
            self.doc = Libxml2Document(response, factory=self._get_libxml2_doc)
            self.xmlNode = self.doc.xmlDoc
        self.expr = expr

    def select(self, xpath):
        if hasattr(self.xmlNode, 'xpathEval'):
            self.doc.xpathContext.setContextNode(self.xmlNode)
            try:
                xpath_result = self.doc.xpathContext.xpathEval(xpath)
            except libxml2.xpathError:
                raise ValueError("Invalid XPath: %s" % xpath)
            if hasattr(xpath_result, '__iter__'):
                return XPathSelectorList([self.__class__(node=node, parent=self, \
                    expr=xpath) for node in xpath_result])
            else:
                return XPathSelectorList([self.__class__(node=xpath_result, \
                    parent=self, expr=xpath)])
        else:
            return XPathSelectorList([])

    def re(self, regex):
        return extract_regex(regex, self.extract())

    def extract(self):
        if isinstance(self.xmlNode, basestring):
            text = unicode(self.xmlNode, 'utf-8', errors='ignore')
        elif hasattr(self.xmlNode, 'serialize'):
            if isinstance(self.xmlNode, libxml2.xmlDoc):
                data = self.xmlNode.getRootElement().serialize('utf-8')
                text = unicode(data, 'utf-8', errors='ignore') if data else u''
            elif isinstance(self.xmlNode, libxml2.xmlAttr): 
                # serialization doesn't work sometimes for xmlAttr types
                text = unicode(self.xmlNode.content, 'utf-8', errors='ignore')
            else:
                data = self.xmlNode.serialize('utf-8')
                text = unicode(data, 'utf-8', errors='ignore') if data else u''
        else:
            try:
                text = unicode(self.xmlNode, 'utf-8', errors='ignore')
            except TypeError:  # catched when self.xmlNode is a float - see tests
                text = unicode(self.xmlNode)
        return text

    def extract_unquoted(self):
        """Get unescaped contents from the text node (no entities, no CDATA)"""
        # TODO: this function should be deprecated. but what would be use instead?
        if self.select('self::text()'):
            return unicode(self.xmlNode.getContent(), 'utf-8', errors='ignore')
        else:
            return u''

    def register_namespace(self, prefix, uri):
        self.doc.xpathContext.xpathRegisterNs(prefix, uri)

    def _get_libxml2_doc(self, response):
        return xmlDoc_from_html(response)

    def __nonzero__(self):
        return bool(self.extract())

    def __str__(self):
        data = repr(self.extract()[:40])
        return "<%s xpath=%r data=%s>" % (type(self).__name__, self.expr, data)

    __repr__ = __str__

    @deprecated(use_instead='XPathSelector.select')
    def __call__(self, xpath):
        return self.select(xpath)

    @deprecated(use_instead='XPathSelector.select')
    def x(self, xpath):
        return self.select(xpath)


class XmlXPathSelector(XPathSelector):
    __slots__ = ()
    _get_libxml2_doc = staticmethod(xmlDoc_from_xml)


class HtmlXPathSelector(XPathSelector):
    __slots__ = ()
    _get_libxml2_doc = staticmethod(xmlDoc_from_html)
