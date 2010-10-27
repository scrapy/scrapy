"""
Selectors tests, specific for lxml backend
"""

from scrapy.http import TextResponse, XmlResponse
has_lxml = True
try:
    from scrapy.selector.lxmlsel import XmlXPathSelector, HtmlXPathSelector, \
        XPathSelector
except ImportError:
    has_lxml = False
from scrapy.utils.test import libxml2debug
from scrapy.tests.test_selector import XPathSelectorTestCase

class XPathSelectorTestCase(XPathSelectorTestCase):

    if has_lxml:
        xs_cls = XPathSelector
        hxs_cls = HtmlXPathSelector
        xxs_cls = XmlXPathSelector
    else:
        skip = "lxml not available"

    @libxml2debug
    def test_selector_boolean_result(self):
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        xs = HtmlXPathSelector(response)
        self.assertEqual(xs.select("//input[@name='a']/@name='a'").extract(), [u'True'])
        self.assertEqual(xs.select("//input[@name='a']/@name='n'").extract(), [u'False'])

    @libxml2debug
    def test_selector_namespaces_simple(self):
        body = """
        <test xmlns:somens="http://scrapy.org">
           <somens:a id="foo">take this</a>
           <a id="bar">found</a>
        </test>
        """

        response = XmlResponse(url="http://example.com", body=body)
        x = XmlXPathSelector(response)
        
        x.register_namespace("somens", "http://scrapy.org")
        self.assertEqual(x.select("//somens:a/text()").extract(),
                         [u'take this'])


    @libxml2debug
    def test_selector_namespaces_multiple(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
<BrowseNode xmlns="http://webservices.amazon.com/AWSECommerceService/2005-10-05"
            xmlns:b="http://somens.com"
            xmlns:p="http://www.scrapy.org/product" >
    <b:Operation>hello</b:Operation>
    <TestTag b:att="value"><Other>value</Other></TestTag>
    <p:SecondTestTag><material>iron</material><price>90</price><p:name>Dried Rose</p:name></p:SecondTestTag>
</BrowseNode>
        """
        response = XmlResponse(url="http://example.com", body=body)
        x = XmlXPathSelector(response)

        x.register_namespace("xmlns", "http://webservices.amazon.com/AWSECommerceService/2005-10-05")
        x.register_namespace("p", "http://www.scrapy.org/product")
        x.register_namespace("b", "http://somens.com")
        self.assertEqual(len(x.select("//xmlns:TestTag")), 1)
        self.assertEqual(x.select("//b:Operation/text()").extract()[0], 'hello')
        self.assertEqual(x.select("//xmlns:TestTag/@b:att").extract()[0], 'value')
        self.assertEqual(x.select("//p:SecondTestTag/xmlns:price/text()").extract()[0], '90')
        self.assertEqual(x.select("//p:SecondTestTag").select("./xmlns:price/text()")[0].extract(), '90')
        self.assertEqual(x.select("//p:SecondTestTag/xmlns:material/text()").extract()[0], 'iron')

    # XXX: this test was disabled because lxml behaves inconsistently when
    # handling null bytes between different 2.2.x versions, but it may be due
    # to differences in libxml2 too. it's also unclear what should be the
    # proper behaviour (pablo - 26 oct 2010)
    #@libxml2debug
    #def test_null_bytes(self):
    #    hxs = HtmlXPathSelector(text='<root>la\x00la</root>')
    #    self.assertEqual(hxs.extract(),
    #                     u'<html><body><root>la</root></body></html>')
    #
    #    xxs = XmlXPathSelector(text='<root>la\x00la</root>')
    #    self.assertEqual(xxs.extract(),
    #                     u'<root>la</root>')
