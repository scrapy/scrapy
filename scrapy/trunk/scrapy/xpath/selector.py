import libxml2

from scrapy.http import Response
from scrapy.xpath.extension import Libxml2Document
from scrapy.xpath.constructors import xmlDoc_from_html
from scrapy.utils.python import flatten
from scrapy.utils.misc import extract_regex

class XPathSelector(object):
    """Provides an easy way for selecting document parts using XPaths and
    regexs, it also supports nested queries.
    
    Usage example (untested code):
    
    x = XPathSelector(response)
    i = ScrapedItem()
    i.assign("name", x.x("//h2/text()"))
    i.assign("features", x.x("//div[@class='features']).x("./span/text()")
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

    def x(self, xpath):
        if hasattr(self.xmlNode, 'xpathEval'):
            self.doc.xpathContext.setContextNode(self.xmlNode)
            xpath_result = self.doc.xpathContext.xpathEval(xpath)
            if hasattr(xpath_result, '__iter__'):
                return XPathSelectorList([XPathSelector(node=node, parent=self, expr=xpath) for node in xpath_result])
            else:
                return XPathSelectorList([XPathSelector(node=xpath_result, parent=self, expr=xpath)])
        else:
            return XPathSelectorList([])

    def re(self, regex):
        return extract_regex(regex, self.extract(), 'utf-8')

    def extract(self, **kwargs): 
        if isinstance(self.xmlNode, basestring):
            text = unicode(self.xmlNode, 'utf-8', errors='ignore')
        elif hasattr(self.xmlNode, 'xpathEval'):
            if isinstance(self.xmlNode, libxml2.xmlAttr):
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

    def register_namespace(self, prefix, uri):
        self.doc.xpathContext.xpathRegisterNs(prefix, uri)

    def __str__(self):
        return "<XPathSelector (%s) xpath=%s>" % (getattr(self.xmlNode, 'name'), self.expr)

    __repr__ = __str__


class XPathSelectorList(list):

    def extract(self, **kwargs):
        return [x.extract(**kwargs) if isinstance(x, XPathSelector) else x for x in self]

    def x(self, xpath):
        return XPathSelectorList(flatten([x.x(xpath) for x in self]))

    def re(self, regex):
        return flatten([x.re(regex) for x in self])
    
