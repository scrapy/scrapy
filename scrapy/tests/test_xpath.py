import re
import unittest

import libxml2

from scrapy.http import TextResponse, HtmlResponse, XmlResponse
from scrapy.xpath.selector import XmlXPathSelector, HtmlXPathSelector
from scrapy.utils.test import libxml2debug

class XPathTestCase(unittest.TestCase):

    @libxml2debug
    def test_selector_simple(self):
        """Simple selector tests"""
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        xpath = HtmlXPathSelector(response)

        xl = xpath.x('//input')
        self.assertEqual(2, len(xl))
        for x in xl:
            assert isinstance(x, HtmlXPathSelector)

        self.assertEqual(xpath.x('//input').extract(),
                         [x.extract() for x in xpath.x('//input')])

        self.assertEqual([x.extract() for x in xpath.x("//input[@name='a']/@name")],
                         [u'a'])
        self.assertEqual([x.extract() for x in xpath.x("number(concat(//input[@name='a']/@value, //input[@name='b']/@value))")],
                         [u'12.0'])

        self.assertEqual(xpath.x("concat('xpath', 'rules')").extract(),
                         [u'xpathrules'])
        self.assertEqual([x.extract() for x in xpath.x("concat(//input[@name='a']/@value, //input[@name='b']/@value)")],
                         [u'12'])

    @libxml2debug
    def test_selector_same_type(self):
        """Test XPathSelector returning the same type in x() method"""
        text = '<p>test<p>'
        assert isinstance(XmlXPathSelector(text=text).x("//p")[0],
                          XmlXPathSelector)
        assert isinstance(HtmlXPathSelector(text=text).x("//p")[0], 
                          HtmlXPathSelector)

    @libxml2debug
    def test_selector_xml_html(self):
        """Test that XML and HTML XPathSelector's behave differently"""

        # some text which is parsed differently by XML and HTML flavors
        text = '<div><img src="a.jpg"><p>Hello</div>'

        self.assertEqual(XmlXPathSelector(text=text).x("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])

        self.assertEqual(HtmlXPathSelector(text=text).x("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></div>'])

    @libxml2debug
    def test_selector_nested(self):
        """Nested selector tests"""
        body = """<body>
                    <div class='one'>
                      <ul>
                        <li>one</li><li>two</li>
                      </ul>
                    </div>
                    <div class='two'>
                      <ul>
                        <li>four</li><li>five</li><li>six</li>
                      </ul>
                    </div>
                  </body>"""

        response = HtmlResponse(url="http://example.com", body=body)
        x = HtmlXPathSelector(response)

        divtwo = x.x('//div[@class="two"]')
        self.assertEqual(divtwo.x("//li").extract(),
                         ["<li>one</li>", "<li>two</li>", "<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.x("./ul/li").extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.x(".//li").extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.x("./li").extract(),
                         [])

    @libxml2debug
    def test_selector_re(self):
        body = """<div>Name: Mary
                    <ul>
                      <li>Name: John</li>
                      <li>Age: 10</li>
                      <li>Name: Paul</li>
                      <li>Age: 20</li>
                    </ul>
                    Age: 20
                  </div>

               """
        response = HtmlResponse(url="http://example.com", body=body)
        x = HtmlXPathSelector(response)

        name_re = re.compile("Name: (\w+)")
        self.assertEqual(x.x("//ul/li").re(name_re),
                         ["John", "Paul"])
        self.assertEqual(x.x("//ul/li").re("Age: (\d+)"),
                         ["10", "20"])

    @libxml2debug
    def test_selector_over_text(self):
        hxs = HtmlXPathSelector(text='<root>lala</root>')
        self.assertEqual(hxs.extract(),
                         u'<html><body><root>lala</root></body></html>')

        xxs = XmlXPathSelector(text='<root>lala</root>')
        self.assertEqual(xxs.extract(),
                         u'<root>lala</root>')

        xxs = XmlXPathSelector(text='<root>lala</root>')
        self.assertEqual(xxs.x('.').extract(),
                         [u'<root>lala</root>'])


    @libxml2debug
    def test_selector_namespaces_simple(self):
        body = """
        <test xmlns:somens="http://scrapy.org">
           <somens:a id="foo"/>
           <a id="bar">found</a>
        </test>
        """

        response = XmlResponse(url="http://example.com", body=body)
        x = XmlXPathSelector(response)
        
        x.register_namespace("somens", "http://scrapy.org")
        self.assertEqual(x.x("//somens:a").extract(), 
                         ['<somens:a id="foo"/>'])


    @libxml2debug
    def test_selector_namespaces_multiple(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
<BrowseNode xmlns="http://webservices.amazon.com/AWSECommerceService/2005-10-05"
            xmlns:b="http://somens.com"
            xmlns:p="http://www.scrapy.org/product" >
    <b:Operation>hello</b:Operation>
    <TestTag b:att="value"><Other>value</Other></TestTag>
    <p:SecondTestTag><material/><price>90</price><p:name>Dried Rose</p:name></p:SecondTestTag>
</BrowseNode>
        """
        response = XmlResponse(url="http://example.com", body=body)
        x = XmlXPathSelector(response)

        x.register_namespace("xmlns", "http://webservices.amazon.com/AWSECommerceService/2005-10-05")
        x.register_namespace("p", "http://www.scrapy.org/product")
        x.register_namespace("b", "http://somens.com")
        self.assertEqual(len(x.x("//xmlns:TestTag")), 1)
        self.assertEqual(x.x("//b:Operation/text()").extract()[0], 'hello')
        self.assertEqual(x.x("//xmlns:TestTag/@b:att").extract()[0], 'value')
        self.assertEqual(x.x("//p:SecondTestTag/xmlns:price/text()").extract()[0], '90')
        self.assertEqual(x.x("//p:SecondTestTag").x("./xmlns:price/text()")[0].extract(), '90')
        self.assertEqual(x.x("//p:SecondTestTag/xmlns:material").extract()[0], '<material/>')

    @libxml2debug
    def test_selector_invalid_xpath(self):
        response = XmlResponse(url="http://example.com", body="<html></html>")
        x = HtmlXPathSelector(response)
        xpath = "//test[@foo='bar]"
        try:
            x.x(xpath)
        except ValueError, e:
            assert xpath in str(e), "Exception message does not contain invalid xpath"
        except Exception:
            raise AssertionError("A invalid XPath does not raise ValueError")
        else:
            raise AssertionError("A invalid XPath does not raise an exception")

    @libxml2debug
    def test_http_header_encoding_precedence(self):
        # u'\xa3'     = pound symbol in unicode
        # u'\xc2\xa3' = pound symbol in utf-8
        # u'\xa3'     = pound symbol in latin-1 (iso-8859-1)

        meta = u'<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        head = u'<head>' + meta + u'</head>'
        body_content = u'<span id="blank">\xa3</span>'
        body = u'<body>' + body_content + u'</body>'
        html = u'<html>' + head + body + u'</html>'
        encoding = 'utf-8'
        html_utf8 = html.encode(encoding)

        headers = {'Content-Type': ['text/html; charset=utf-8']}
        response = HtmlResponse(url="http://example.com", headers=headers, body=html_utf8)
        x = HtmlXPathSelector(response)
        self.assertEquals(x.x("//span[@id='blank']/text()").extract(),
                          [u'\xa3'])

    @libxml2debug
    def test_null_bytes(self):
        hxs = HtmlXPathSelector(text='<root>la\x00la</root>')
        self.assertEqual(hxs.extract(),
                         u'<html><body><root>lala</root></body></html>')

        xxs = XmlXPathSelector(text='<root>la\x00la</root>')
        self.assertEqual(xxs.extract(),
                         u'<root>lala</root>')

    @libxml2debug
    def test_unquote(self):
        xmldoc = '\n'.join((
            '<root>',
            '  lala',
            '  <node>',
            '    blabla&amp;more<!--comment-->a<b>test</b>oh',
            '    <![CDATA[lalalal&ppppp<b>PPPP</b>ppp&amp;la]]>',
            '  </node>',
            '  pff',
            '</root>'))
        xxs = XmlXPathSelector(text=xmldoc)

        self.assertEqual(xxs.extract_unquoted(), u'')

        self.assertEqual(xxs.x('/root').extract_unquoted(), [u''])
        self.assertEqual(xxs.x('/root/text()').extract_unquoted(), [
            u'\n  lala\n  ',
            u'\n  pff\n'])

        self.assertEqual(xxs.x('//*').extract_unquoted(), [u'', u'', u''])
        self.assertEqual(xxs.x('//text()').extract_unquoted(), [
            u'\n  lala\n  ',
            u'\n    blabla&more',
            u'a',
            u'test',
            u'oh\n    ',
            u'lalalal&ppppp<b>PPPP</b>ppp&amp;la',
            u'\n  ',
            u'\n  pff\n'])

if __name__ == "__main__":
    unittest.main()
