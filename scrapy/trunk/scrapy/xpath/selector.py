import libxml2

from scrapy.http import Response
from scrapy.xpath.extension import Libxml2Document
from scrapy.xpath.constructors import xmlDoc_from_html, xmlDoc_from_xml
from scrapy.utils.python import flatten
from scrapy.utils.misc import extract_regex

class XPathSelector(object):
    """The XPathSelector class provides a convenient way for selecting document
    parts using XPaths and regexs, with support for nested queries.

    Although this is not an abstract class, you usually instantiate one of its
    children:
    
    - XmlXPathSelector (for XML content)
    - HtmlXPathSelector (for HTML content)
    """

    def __init__(self, response=None, text=None, node=None, parent=None, expr=None, constructor=xmlDoc_from_html):
        if parent:
            self.doc = parent.doc
            self.xmlNode = node
        elif response:
            try:
                self.doc = response.getlibxml2doc(constructor=constructor)  # try with cached version first
            except AttributeError:
                self.doc = Libxml2Document(response, constructor=constructor)
            self.xmlNode = self.doc.xmlDoc
        elif text:
            response = Response(domain=None, url=None, body=str(text))
            self.doc = Libxml2Document(response, constructor=constructor)
            self.xmlNode = self.doc.xmlDoc
        self.expr = expr
        self.response = response

    def x(self, xpath):
        """Perform the given XPath query on the current XPathSelector and
        return a XPathSelectorList of the result"""
        if hasattr(self.xmlNode, 'xpathEval'):
            self.doc.xpathContext.setContextNode(self.xmlNode)
            xpath_result = self.doc.xpathContext.xpathEval(xpath)
            cls = type(self)
            if hasattr(xpath_result, '__iter__'):
                return XPathSelectorList([cls(node=node, parent=self, expr=xpath, response=self.response)
                                          for node in xpath_result])
            else:
                return XPathSelectorList([cls(node=xpath_result, parent=self, expr=xpath, response=self.response)])
        else:
            return XPathSelectorList([])

    def re(self, regex):
        """Return a list of unicode strings by applying the regex over all
        current XPath selections, and flattening the results"""
        return extract_regex(regex, self.extract(), 'utf-8')

    def extract(self):
        """Return a unicode string of the content referenced by the XPathSelector"""
        if isinstance(self.xmlNode, basestring):
            text = unicode(self.xmlNode, 'utf-8', errors='ignore')
        elif hasattr(self.xmlNode, 'serialize'):
            if isinstance(self.xmlNode, libxml2.xmlDoc):
                data = self.xmlNode.getRootElement().serialize('utf-8')
                text = unicode(data, 'utf-8', errors='ignore') if data else u''
            elif isinstance(self.xmlNode, libxml2.xmlAttr): 
                # serialization doesn't work sometimes for xmlAttr types
                text = unicode(self.xmlNode.content, errors='ignore')
            else:
                data = self.xmlNode.serialize('utf-8')
                text = unicode(data, 'utf-8', errors='ignore') if data else u''
        else:
            try:
                text = unicode(self.xmlNode, errors='ignore')
            except TypeError:  # catched when self.xmlNode is a float - see tests
                text = unicode(self.xmlNode)
        return text

    def extract_unquoted(self):
        """Get unescaped contents from the text node (no entities, no CDATA)"""
        if self.x('self::text()'):
            return unicode(self.xmlNode.getContent(), errors='ignore')
        else:
            return u''

    def register_namespace(self, prefix, uri):
        """Register namespace so that it can be used in XPath queries"""
        self.doc.xpathContext.xpathRegisterNs(prefix, uri)

    def __nonzero__(self):
        return bool(self.extract())

    def __str__(self):
        return "<%s (%s) xpath=%s>" % (type(self).__name__, getattr(self.xmlNode, 'name', type(self.xmlNode).__name__), self.expr)

    __repr__ = __str__


class XPathSelectorList(list):
    """List of XPathSelector objects"""

    def __getslice__(self, i, j):
        return XPathSelectorList(list.__getslice__(self, i, j))

    def x(self, xpath):
        """Perform the given XPath query on each XPathSelector of the list and
        return a new (flattened) XPathSelectorList of the results"""
        return XPathSelectorList(flatten([x.x(xpath) for x in self]))

    def re(self, regex):
        """Perform the re() method on each XPathSelector of the list, and
        return the result as a flattened list of unicode strings"""
        return flatten([x.re(regex) for x in self])

    def extract(self):
        """Return a list of unicode strings with the content referenced by each
        XPathSelector of the list"""
        return [x.extract() if isinstance(x, XPathSelector) else x for x in self]

    def extract_unquoted(self):
        return [x.extract_unquoted() if isinstance(x, XPathSelector) else x for x in self]


class XmlXPathSelector(XPathSelector):
    """XPathSelector for XML content"""
    def __init__(self, *args, **kwargs):
        kwargs['constructor'] = xmlDoc_from_xml
        XPathSelector.__init__(self, *args, **kwargs)

class HtmlXPathSelector(XPathSelector):
    """XPathSelector for HTML content"""
    def __init__(self, *args, **kwargs):
        kwargs['constructor'] = xmlDoc_from_html
        XPathSelector.__init__(self, *args, **kwargs)
