"""
Selectors tests, common for all backends
"""

import re
import weakref

from twisted.trial import unittest

from scrapy.http import TextResponse, HtmlResponse, XmlResponse
from scrapy.selector import XmlXPathSelector, HtmlXPathSelector, \
    XPathSelector
from scrapy.utils.test import libxml2debug

class XPathSelectorTestCase(unittest.TestCase):

    xs_cls = XPathSelector
    hxs_cls = HtmlXPathSelector
    xxs_cls = XmlXPathSelector

    @libxml2debug
    def test_selector_simple(self):
        """Simple selector tests"""
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        xpath = self.hxs_cls(response)

        xl = xpath.select('//input')
        self.assertEqual(2, len(xl))
        for x in xl:
            assert isinstance(x, self.hxs_cls)

        self.assertEqual(xpath.select('//input').extract(),
                         [x.extract() for x in xpath.select('//input')])

        self.assertEqual([x.extract() for x in xpath.select("//input[@name='a']/@name")],
                         [u'a'])
        self.assertEqual([x.extract() for x in xpath.select("number(concat(//input[@name='a']/@value, //input[@name='b']/@value))")],
                         [u'12.0'])

        self.assertEqual(xpath.select("concat('xpath', 'rules')").extract(),
                         [u'xpathrules'])
        self.assertEqual([x.extract() for x in xpath.select("concat(//input[@name='a']/@value, //input[@name='b']/@value)")],
                         [u'12'])

    @libxml2debug
    def test_selector_unicode_query(self):
        body = u"<p><input name='\xa9' value='1'/></p>"
        response = TextResponse(url="http://example.com", body=body, encoding='utf8')
        xpath = self.hxs_cls(response)
        self.assertEqual(xpath.select(u'//input[@name="\xa9"]/@value').extract(), [u'1'])

    @libxml2debug
    def test_selector_same_type(self):
        """Test XPathSelector returning the same type in x() method"""
        text = '<p>test<p>'
        assert isinstance(self.xxs_cls(text=text).select("//p")[0],
                          self.xxs_cls)
        assert isinstance(self.hxs_cls(text=text).select("//p")[0], 
                          self.hxs_cls)

    @libxml2debug
    def test_selector_boolean_result(self):
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        xs = self.hxs_cls(response)
        self.assertEquals(xs.select("//input[@name='a']/@name='a'").extract(), [u'1'])
        self.assertEquals(xs.select("//input[@name='a']/@name='n'").extract(), [u'0'])

    @libxml2debug
    def test_selector_xml_html(self):
        """Test that XML and HTML XPathSelector's behave differently"""

        # some text which is parsed differently by XML and HTML flavors
        text = '<div><img src="a.jpg"><p>Hello</div>'

        self.assertEqual(self.xxs_cls(text=text).select("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])

        self.assertEqual(self.hxs_cls(text=text).select("//div").extract(),
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
        x = self.hxs_cls(response)

        divtwo = x.select('//div[@class="two"]')
        self.assertEqual(map(unicode.strip, divtwo.select("//li").extract()),
                         ["<li>one</li>", "<li>two</li>", "<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(map(unicode.strip, divtwo.select("./ul/li").extract()),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(map(unicode.strip, divtwo.select(".//li").extract()),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.select("./li").extract(),
                         [])

    @libxml2debug
    def test_dont_strip(self):
        hxs = self.hxs_cls(text='<div>fff: <a href="#">zzz</a></div>')
        self.assertEqual(hxs.select("//text()").extract(),
            [u'fff: ', u'zzz'])

    @libxml2debug
    def test_selector_namespaces_simple(self):
        body = """
        <test xmlns:somens="http://scrapy.org">
           <somens:a id="foo">take this</a>
           <a id="bar">found</a>
        </test>
        """

        response = XmlResponse(url="http://example.com", body=body)
        x = self.xxs_cls(response)

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
        x = self.xxs_cls(response)

        x.register_namespace("xmlns", "http://webservices.amazon.com/AWSECommerceService/2005-10-05")
        x.register_namespace("p", "http://www.scrapy.org/product")
        x.register_namespace("b", "http://somens.com")
        self.assertEqual(len(x.select("//xmlns:TestTag")), 1)
        self.assertEqual(x.select("//b:Operation/text()").extract()[0], 'hello')
        self.assertEqual(x.select("//xmlns:TestTag/@b:att").extract()[0], 'value')
        self.assertEqual(x.select("//p:SecondTestTag/xmlns:price/text()").extract()[0], '90')
        self.assertEqual(x.select("//p:SecondTestTag").select("./xmlns:price/text()")[0].extract(), '90')
        self.assertEqual(x.select("//p:SecondTestTag/xmlns:material/text()").extract()[0], 'iron')

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
        x = self.hxs_cls(response)

        name_re = re.compile("Name: (\w+)")
        self.assertEqual(x.select("//ul/li").re(name_re),
                         ["John", "Paul"])
        self.assertEqual(x.select("//ul/li").re("Age: (\d+)"),
                         ["10", "20"])

    @libxml2debug
    def test_selector_re_intl(self):
        body = """<div>Evento: cumplea\xc3\xb1os</div>"""
        response = HtmlResponse(url="http://example.com", body=body, encoding='utf-8')
        x = self.hxs_cls(response)
        self.assertEqual(x.select("//div").re("Evento: (\w+)"), [u'cumplea\xf1os'])

    @libxml2debug
    def test_selector_over_text(self):
        hxs = self.hxs_cls(text='<root>lala</root>')
        self.assertEqual(hxs.extract(),
                         u'<html><body><root>lala</root></body></html>')

        xxs = self.xxs_cls(text='<root>lala</root>')
        self.assertEqual(xxs.extract(),
                         u'<root>lala</root>')

        xxs = self.xxs_cls(text='<root>lala</root>')
        self.assertEqual(xxs.select('.').extract(),
                         [u'<root>lala</root>'])


    @libxml2debug
    def test_selector_invalid_xpath(self):
        response = XmlResponse(url="http://example.com", body="<html></html>")
        x = self.hxs_cls(response)
        xpath = "//test[@foo='bar]"
        try:
            x.select(xpath)
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
        x = self.hxs_cls(response)
        self.assertEquals(x.select("//span[@id='blank']/text()").extract(),
                          [u'\xa3'])

    @libxml2debug
    def test_empty_bodies(self):
        # shouldn't raise errors
        r1 = TextResponse('http://www.example.com', body='')
        self.hxs_cls(r1).select('//text()').extract()
        self.xxs_cls(r1).select('//text()').extract()

    @libxml2debug
    def test_null_bytes(self):
        # shouldn't raise errors
        r1 = TextResponse('http://www.example.com', \
                          body='<root>pre\x00post</root>', \
                          encoding='utf-8')
        self.hxs_cls(r1).select('//text()').extract()
        self.xxs_cls(r1).select('//text()').extract()

    @libxml2debug
    def test_badly_encoded_body(self):
        # \xe9 alone isn't valid utf8 sequence
        r1 = TextResponse('http://www.example.com', \
                          body='<html><p>an Jos\xe9 de</p><html>', \
                          encoding='utf-8')
        self.hxs_cls(r1).select('//text()').extract()
        self.xxs_cls(r1).select('//text()').extract()

    @libxml2debug
    def test_select_on_unevaluable_nodes(self):
        r = self.hxs_cls(text=u'<span class="big">some text</span>')
        # Text node
        x1 = r.select('//text()')
        self.assertEquals(x1.extract(), [u'some text'])
        self.assertEquals(x1.select('.//b').extract(), [])
        # Tag attribute
        x1 = r.select('//span/@class')
        self.assertEquals(x1.extract(), [u'big'])
        self.assertEquals(x1.select('.//text()').extract(), [])

    @libxml2debug
    def test_select_on_text_nodes(self):
        r = self.hxs_cls(text=u'<div><b>Options:</b>opt1</div><div><b>Other</b>opt2</div>')
        x1 = r.select("//div/descendant::text()[preceding-sibling::b[contains(text(), 'Options')]]")
        self.assertEquals(x1.extract(), [u'opt1'])

        x1 = r.select("//div/descendant::text()/preceding-sibling::b[contains(text(), 'Options')]")
        self.assertEquals(x1.extract(), [u'<b>Options:</b>'])

    @libxml2debug
    def test_nested_select_on_text_nodes(self):
        # FIXME: does not work with lxml backend [upstream]
        r = self.hxs_cls(text=u'<div><b>Options:</b>opt1</div><div><b>Other</b>opt2</div>')
        x1 = r.select("//div/descendant::text()")
        x2 = x1.select("./preceding-sibling::b[contains(text(), 'Options')]")

        self.assertEquals(x2.extract(), [u'<b>Options:</b>'])
    test_nested_select_on_text_nodes.skip = True

    @libxml2debug
    def test_weakref_slots(self):
        """Check that classes are using slots and are weak-referenceable"""
        for cls in [self.xs_cls, self.hxs_cls, self.xxs_cls]:
            x = cls()
            weakref.ref(x)
            assert not hasattr(x, '__dict__'), "%s does not use __slots__" % \
                x.__class__.__name__
