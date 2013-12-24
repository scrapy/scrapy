import re
import warnings
import weakref
from twisted.trial import unittest
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import TextResponse, HtmlResponse, XmlResponse
from scrapy.selector import Selector, XPath, CSS
from scrapy.selector.lxmlsel import XmlXPathSelector, HtmlXPathSelector, XPathSelector


class SelectorTestCase(unittest.TestCase):

    sscls = Selector

    def test_simple_selection(self):
        """Simple selector tests"""
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        sel = self.sscls(response)

        xl = sel.xpath('//input')
        self.assertEqual(2, len(xl))
        for x in xl:
            assert isinstance(x, self.sscls)

        self.assertEqual(sel.xpath('//input').extract(),
                         [x.extract() for x in sel.xpath('//input')])

        self.assertEqual([x.extract() for x in sel.xpath("//input[@name='a']/@name")],
                         [u'a'])
        self.assertEqual([x.extract() for x in sel.xpath("number(concat(//input[@name='a']/@value, //input[@name='b']/@value))")],
                         [u'12.0'])

        self.assertEqual(sel.xpath("concat('xpath', 'rules')").extract(),
                         [u'xpathrules'])
        self.assertEqual([x.extract() for x in sel.xpath("concat(//input[@name='a']/@value, //input[@name='b']/@value)")],
                         [u'12'])

    def test_select_unicode_query(self):
        body = u"<p><input name='\xa9' value='1'/></p>"
        response = TextResponse(url="http://example.com", body=body, encoding='utf8')
        sel = self.sscls(response)
        self.assertEqual(sel.xpath(u'//input[@name="\xa9"]/@value').extract(), [u'1'])

    def test_list_elements_type(self):
        """Test Selector returning the same type in selection methods"""
        text = '<p>test<p>'
        assert isinstance(self.sscls(text=text).xpath("//p")[0], self.sscls)
        assert isinstance(self.sscls(text=text).css("p")[0], self.sscls)

    def test_boolean_result(self):
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        xs = self.sscls(response)
        self.assertEquals(xs.xpath("//input[@name='a']/@name='a'").extract(), [u'1'])
        self.assertEquals(xs.xpath("//input[@name='a']/@name='n'").extract(), [u'0'])

    def test_differences_parsing_xml_vs_html(self):
        """Test that XML and HTML Selector's behave differently"""
        # some text which is parsed differently by XML and HTML flavors
        text = '<div><img src="a.jpg"><p>Hello</div>'
        hs = self.sscls(text=text, type='html')
        self.assertEqual(hs.xpath("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></div>'])

        xs = self.sscls(text=text, type='xml')
        self.assertEqual(xs.xpath("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])

    def test_flavor_detection(self):
        text = '<div><img src="a.jpg"><p>Hello</div>'
        sel = self.sscls(XmlResponse('http://example.com', body=text))
        self.assertEqual(sel.type, 'xml')
        self.assertEqual(sel.xpath("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])

        sel = self.sscls(HtmlResponse('http://example.com', body=text))
        self.assertEqual(sel.type, 'html')
        self.assertEqual(sel.xpath("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></div>'])

    def test_nested_selectors(self):
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
        x = self.sscls(response)
        divtwo = x.xpath('//div[@class="two"]')
        self.assertEqual(divtwo.xpath("//li").extract(),
                         ["<li>one</li>", "<li>two</li>", "<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.xpath("./ul/li").extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.xpath(".//li").extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.xpath("./li").extract(), [])

    def test_mixed_nested_selectors(self):
        body = '''<body>
                    <div id=1>not<span>me</span></div>
                    <div class="dos"><p>text</p><a href='#'>foo</a></div>
               </body>'''
        sel = self.sscls(text=body)
        self.assertEqual(sel.xpath('//div[@id="1"]').css('span::text').extract(), [u'me'])
        self.assertEqual(sel.css('#1').xpath('./span/text()').extract(), [u'me'])

    def test_dont_strip(self):
        sel = self.sscls(text='<div>fff: <a href="#">zzz</a></div>')
        self.assertEqual(sel.xpath("//text()").extract(), [u'fff: ', u'zzz'])

    def test_namespaces_simple(self):
        body = """
        <test xmlns:somens="http://scrapy.org">
           <somens:a id="foo">take this</a>
           <a id="bar">found</a>
        </test>
        """

        response = XmlResponse(url="http://example.com", body=body)
        x = self.sscls(response)

        x.register_namespace("somens", "http://scrapy.org")
        self.assertEqual(x.xpath("//somens:a/text()").extract(),
                         [u'take this'])

    def test_namespaces_multiple(self):
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
        x = self.sscls(response)
        x.register_namespace("xmlns", "http://webservices.amazon.com/AWSECommerceService/2005-10-05")
        x.register_namespace("p", "http://www.scrapy.org/product")
        x.register_namespace("b", "http://somens.com")
        self.assertEqual(len(x.xpath("//xmlns:TestTag")), 1)
        self.assertEqual(x.xpath("//b:Operation/text()").extract()[0], 'hello')
        self.assertEqual(x.xpath("//xmlns:TestTag/@b:att").extract()[0], 'value')
        self.assertEqual(x.xpath("//p:SecondTestTag/xmlns:price/text()").extract()[0], '90')
        self.assertEqual(x.xpath("//p:SecondTestTag").xpath("./xmlns:price/text()")[0].extract(), '90')
        self.assertEqual(x.xpath("//p:SecondTestTag/xmlns:material/text()").extract()[0], 'iron')

    def test_re(self):
        body = """<div>Name: Mary
                    <ul>
                      <li>Name: John</li>
                      <li>Age: 10</li>
                      <li>Name: Paul</li>
                      <li>Age: 20</li>
                    </ul>
                    Age: 20
                  </div>"""
        response = HtmlResponse(url="http://example.com", body=body)
        x = self.sscls(response)

        name_re = re.compile("Name: (\w+)")
        self.assertEqual(x.xpath("//ul/li").re(name_re),
                         ["John", "Paul"])
        self.assertEqual(x.xpath("//ul/li").re("Age: (\d+)"),
                         ["10", "20"])

    def test_re_intl(self):
        body = """<div>Evento: cumplea\xc3\xb1os</div>"""
        response = HtmlResponse(url="http://example.com", body=body, encoding='utf-8')
        x = self.sscls(response)
        self.assertEqual(x.xpath("//div").re("Evento: (\w+)"), [u'cumplea\xf1os'])

    def test_selector_over_text(self):
        hs = self.sscls(text='<root>lala</root>')
        self.assertEqual(hs.extract(), u'<html><body><root>lala</root></body></html>')
        xs = self.sscls(text='<root>lala</root>', type='xml')
        self.assertEqual(xs.extract(), u'<root>lala</root>')
        self.assertEqual(xs.xpath('.').extract(), [u'<root>lala</root>'])

    def test_invalid_xpath(self):
        response = XmlResponse(url="http://example.com", body="<html></html>")
        x = self.sscls(response)
        xpath = "//test[@foo='bar]"
        try:
            x.xpath(xpath)
        except ValueError as e:
            assert xpath in str(e), "Exception message does not contain invalid xpath"
        except Exception:
            raise AssertionError("A invalid XPath does not raise ValueError")
        else:
            raise AssertionError("A invalid XPath does not raise an exception")

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
        x = self.sscls(response)
        self.assertEquals(x.xpath("//span[@id='blank']/text()").extract(),
                          [u'\xa3'])

    def test_empty_bodies(self):
        # shouldn't raise errors
        r1 = TextResponse('http://www.example.com', body='')
        self.sscls(r1).xpath('//text()').extract()

    def test_null_bytes(self):
        # shouldn't raise errors
        r1 = TextResponse('http://www.example.com', \
                          body='<root>pre\x00post</root>', \
                          encoding='utf-8')
        self.sscls(r1).xpath('//text()').extract()

    def test_badly_encoded_body(self):
        # \xe9 alone isn't valid utf8 sequence
        r1 = TextResponse('http://www.example.com', \
                          body='<html><p>an Jos\xe9 de</p><html>', \
                          encoding='utf-8')
        self.sscls(r1).xpath('//text()').extract()

    def test_select_on_unevaluable_nodes(self):
        r = self.sscls(text=u'<span class="big">some text</span>')
        # Text node
        x1 = r.xpath('//text()')
        self.assertEquals(x1.extract(), [u'some text'])
        self.assertEquals(x1.xpath('.//b').extract(), [])
        # Tag attribute
        x1 = r.xpath('//span/@class')
        self.assertEquals(x1.extract(), [u'big'])
        self.assertEquals(x1.xpath('.//text()').extract(), [])

    def test_select_on_text_nodes(self):
        r = self.sscls(text=u'<div><b>Options:</b>opt1</div><div><b>Other</b>opt2</div>')
        x1 = r.xpath("//div/descendant::text()[preceding-sibling::b[contains(text(), 'Options')]]")
        self.assertEquals(x1.extract(), [u'opt1'])

        x1 = r.xpath("//div/descendant::text()/preceding-sibling::b[contains(text(), 'Options')]")
        self.assertEquals(x1.extract(), [u'<b>Options:</b>'])

    def test_nested_select_on_text_nodes(self):
        # FIXME: does not work with lxml backend [upstream]
        r = self.sscls(text=u'<div><b>Options:</b>opt1</div><div><b>Other</b>opt2</div>')
        x1 = r.xpath("//div/descendant::text()")
        x2 = x1.xpath("./preceding-sibling::b[contains(text(), 'Options')]")
        self.assertEquals(x2.extract(), [u'<b>Options:</b>'])
    test_nested_select_on_text_nodes.skip = "Text nodes lost parent node reference in lxml"

    def test_weakref_slots(self):
        """Check that classes are using slots and are weak-referenceable"""
        x = self.sscls()
        weakref.ref(x)
        assert not hasattr(x, '__dict__'), "%s does not use __slots__" % \
            x.__class__.__name__

    def test_remove_namespaces(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-US" xmlns:media="http://search.yahoo.com/mrss/">
  <link type="text/html">
  <link type="application/atom+xml">
</feed>
"""
        sel = self.sscls(XmlResponse("http://example.com/feed.atom", body=xml))
        self.assertEqual(len(sel.xpath("//link")), 0)
        sel.remove_namespaces()
        self.assertEqual(len(sel.xpath("//link")), 2)

    def test_remove_attributes_namespaces(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:atom="http://www.w3.org/2005/Atom" xml:lang="en-US" xmlns:media="http://search.yahoo.com/mrss/">
  <link atom:type="text/html">
  <link atom:type="application/atom+xml">
</feed>
"""
        sel = self.sscls(XmlResponse("http://example.com/feed.atom", body=xml))
        self.assertEqual(len(sel.xpath("//link/@type")), 0)
        sel.remove_namespaces()
        self.assertEqual(len(sel.xpath("//link/@type")), 2)


class CompiledSelectorTestCase(unittest.TestCase):

    sscls = Selector

    def test_simple_selection(self):
        """Simple selector tests"""

        xp_input = XPath('//input')
        xp_input_name = XPath("//input[@name='a']/@name")
        xp_number_concat = XPath(
            "number(concat(//input[@name='a']/@value, //input[@name='b']/@value))")
        xp_concat = XPath("concat('xpath', 'rules')")
        xp_concat_value = XPath("concat(//input[@name='a']/@value, //input[@name='b']/@value)")

        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        sel = self.sscls(response)

        xl = sel.xpath(xp_input)
        self.assertEqual(2, len(xl))
        for x in xl:
            assert isinstance(x, self.sscls)

        self.assertEqual(sel.xpath(xp_input).extract(),
                         [x.extract() for x in sel.xpath(xp_input)])

        self.assertEqual([x.extract() for x in sel.xpath(xp_input_name)],
                         [u'a'])
        self.assertEqual([x.extract() for x in sel.xpath(xp_number_concat)],
                         [u'12.0'])

        self.assertEqual(sel.xpath(xp_concat).extract(),
                         [u'xpathrules'])
        self.assertEqual([x.extract() for x in sel.xpath(xp_concat_value)],
                         [u'12'])

    def test_select_unicode_query(self):
        xp_input_value = XPath(u'//input[@name="\xa9"]/@value')
        body = u"<p><input name='\xa9' value='1'/></p>"
        response = TextResponse(url="http://example.com", body=body, encoding='utf8')
        sel = self.sscls(response)
        self.assertEqual(sel.xpath(xp_input_value).extract(), [u'1'])

    def test_list_elements_type(self):
        """Test Selector returning the same type in selection methods"""
        text = '<p>test<p>'
        xp_p = XPath("//p")
        css_p = CSS("p")
        assert isinstance(self.sscls(text=text).xpath(xp_p)[0], self.sscls)
        assert isinstance(self.sscls(text=text).css(css_p)[0], self.sscls)

    def test_boolean_result(self):
        body = "<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body)
        xp_name_a = XPath("//input[@name='a']/@name='a'")
        xp_name_n = XPath("//input[@name='a']/@name='n'")
        xs = self.sscls(response)
        self.assertEquals(xs.xpath(xp_name_a).extract(), [u'1'])
        self.assertEquals(xs.xpath(xp_name_n).extract(), [u'0'])

    def test_differences_parsing_xml_vs_html(self):
        """Test that XML and HTML Selector's behave differently"""
        # some text which is parsed differently by XML and HTML flavors
        text = '<div><img src="a.jpg"><p>Hello</div>'
        xp_div = XPath("//div")
        hs = self.sscls(text=text, type='html')
        self.assertEqual(hs.xpath(xp_div).extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></div>'])

        xs = self.sscls(text=text, type='xml')
        self.assertEqual(xs.xpath(xp_div).extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])

    def test_flavor_detection(self):
        text = '<div><img src="a.jpg"><p>Hello</div>'
        xp_div = XPath("//div")
        sel = self.sscls(XmlResponse('http://example.com', body=text))
        self.assertEqual(sel.type, 'xml')
        self.assertEqual(sel.xpath(xp_div).extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])

        sel = self.sscls(HtmlResponse('http://example.com', body=text))
        self.assertEqual(sel.type, 'html')
        self.assertEqual(sel.xpath(xp_div).extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></div>'])

    def test_nested_selectors(self):
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

        xp_div_two = XPath('//div[@class="two"]')
        xp_all_li = XPath("//li")
        xp_ul_li = XPath("./ul/li")
        xp_desc_li = XPath(".//li")
        xp_child_li = XPath("./li")

        x = self.sscls(response)
        divtwo = x.xpath(xp_div_two)
        self.assertEqual(divtwo.xpath(xp_all_li).extract(),
                         ["<li>one</li>", "<li>two</li>", "<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.xpath(xp_ul_li).extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.xpath(xp_desc_li).extract(),
                         ["<li>four</li>", "<li>five</li>", "<li>six</li>"])
        self.assertEqual(divtwo.xpath(xp_child_li).extract(), [])

    def test_mixed_nested_selectors(self):
        body = '''<body>
                    <div id=1>not<span>me</span></div>
                    <div class="dos"><p>text</p><a href='#'>foo</a></div>
               </body>'''
        xp_div_id1 = XPath('//div[@id="1"]')
        css_span_text = CSS('span::text')
        css_id1 = CSS('#1')
        xp_span_text = XPath('./span/text()')

        sel = self.sscls(text=body)
        self.assertEqual(sel.xpath(xp_div_id1).css(css_span_text).extract(), [u'me'])
        self.assertEqual(sel.css(css_id1).xpath(xp_span_text).extract(), [u'me'])

    def test_dont_strip(self):
        xp_text = XPath("//text()")
        sel = self.sscls(text='<div>fff: <a href="#">zzz</a></div>')
        self.assertEqual(sel.xpath(xp_text).extract(), [u'fff: ', u'zzz'])

    def test_namespaces_simple(self):
        body = """
        <test xmlns:somens="http://scrapy.org">
           <somens:a id="foo">take this</a>
           <a id="bar">found</a>
        </test>
        """

        response = XmlResponse(url="http://example.com", body=body)

        xp_somens_a_text = XPath("//somens:a/text()",
            namespaces={"somens":"http://scrapy.org"})
        x = self.sscls(response)
        self.assertEqual(x.xpath(xp_somens_a_text).extract(),
                         [u'take this'])

        xp_somens_a_text = XPath("//somens:a/text()")
        xp_somens_a_text.register_namespace("somens", "http://scrapy.org")
        self.assertEqual(x.xpath(xp_somens_a_text).extract(),
                         [u'take this'])

    def test_namespaces_multiple(self):
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

        xp_testtag = XPath("//xmlns:TestTag", namespaces={
                "xmlns": "http://webservices.amazon.com/AWSECommerceService/2005-10-05"
            })
        xp_operation_text = XPath("//b:Operation/text()", namespaces={
                "b": "http://somens.com"
            })
        xp_testtag_att = XPath("//xmlns:TestTag/@b:att", namespaces={
                "xmlns": "http://webservices.amazon.com/AWSECommerceService/2005-10-05",
                "b": "http://somens.com"
            })
        xp_secondtesttag_price_text = XPath("//p:SecondTestTag/xmlns:price/text()", namespaces={
                "p": "http://www.scrapy.org/product",
                "xmlns": "http://webservices.amazon.com/AWSECommerceService/2005-10-05",
            })
        xp_secondtesttag = XPath("//p:SecondTestTag", namespaces={
                "p": "http://www.scrapy.org/product",
            })
        xp_secondtesttag_material = XPath("//p:SecondTestTag/xmlns:material/text()", namespaces={
                "p": "http://www.scrapy.org/product",
                "xmlns": "http://webservices.amazon.com/AWSECommerceService/2005-10-05",
            })

        x = self.sscls(response)

        self.assertEqual(len(x.xpath(xp_testtag)), 1)
        self.assertEqual(x.xpath(xp_operation_text).extract()[0], 'hello')
        self.assertEqual(x.xpath(xp_testtag_att).extract()[0], 'value')
        self.assertEqual(x.xpath(xp_secondtesttag_price_text).extract()[0], '90')

        x.register_namespace("xmlns", "http://webservices.amazon.com/AWSECommerceService/2005-10-05")
        self.assertEqual(x.xpath(xp_secondtesttag).xpath("./xmlns:price/text()")[0].extract(), '90')
        self.assertEqual(x.xpath(xp_secondtesttag_material).extract()[0], 'iron')

    def test_re(self):
        body = """<div>Name: Mary
                    <ul>
                      <li>Name: John</li>
                      <li>Age: 10</li>
                      <li>Name: Paul</li>
                      <li>Age: 20</li>
                    </ul>
                    Age: 20
                  </div>"""
        response = HtmlResponse(url="http://example.com", body=body)
        xp_ul_li = XPath("//ul/li")
        x = self.sscls(response)

        name_re = re.compile("Name: (\w+)")
        self.assertEqual(x.xpath(xp_ul_li).re(name_re),
                         ["John", "Paul"])
        self.assertEqual(x.xpath(xp_ul_li).re("Age: (\d+)"),
                         ["10", "20"])

    def test_re_intl(self):
        body = """<div>Evento: cumplea\xc3\xb1os</div>"""
        response = HtmlResponse(url="http://example.com", body=body, encoding='utf-8')
        xp_div = XPath("//div")
        x = self.sscls(response)
        self.assertEqual(x.xpath(xp_div).re("Evento: (\w+)"), [u'cumplea\xf1os'])

    def test_selector_over_text(self):
        hs = self.sscls(text='<root>lala</root>')
        xp_over_text = XPath('.')
        self.assertEqual(hs.extract(), u'<html><body><root>lala</root></body></html>')
        xs = self.sscls(text='<root>lala</root>', type='xml')
        self.assertEqual(xs.extract(), u'<root>lala</root>')
        self.assertEqual(xs.xpath(xp_over_text).extract(), [u'<root>lala</root>'])

    def test_invalid_xpath(self):
        response = XmlResponse(url="http://example.com", body="<html></html>")
        x = self.sscls(response)
        xpath = "//test[@foo='bar]"
        xp = XPath(xpath)
        try:
            x.xpath(xp)
        except ValueError as e:
            assert xpath in str(e), "Exception message does not contain invalid xpath"
        except Exception as e:
            raise AssertionError("A invalid XPath does not raise ValueError; raised %r" % type(e))
        else:
            raise AssertionError("A invalid XPath does not raise an exception")

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
        xp_span_blank_text = XPath("//span[@id='blank']/text()")
        response = HtmlResponse(url="http://example.com", headers=headers, body=html_utf8)
        x = self.sscls(response)
        self.assertEquals(x.xpath(xp_span_blank_text).extract(),
                          [u'\xa3'])

    def test_empty_bodies(self):
        # shouldn't raise errors
        r1 = TextResponse('http://www.example.com', body='')
        xp_text = XPath('//text()')
        self.sscls(r1).xpath(xp_text).extract()

    def test_null_bytes(self):
        # shouldn't raise errors
        r1 = TextResponse('http://www.example.com', \
                          body='<root>pre\x00post</root>', \
                          encoding='utf-8')
        xp_text = XPath('//text()')
        self.sscls(r1).xpath(xp_text).extract()

    def test_badly_encoded_body(self):
        # \xe9 alone isn't valid utf8 sequence
        r1 = TextResponse('http://www.example.com', \
                          body='<html><p>an Jos\xe9 de</p><html>', \
                          encoding='utf-8')
        xp_text = XPath('//text()')
        self.sscls(r1).xpath(xp_text).extract()

    def test_select_on_unevaluable_nodes(self):
        r = self.sscls(text=u'<span class="big">some text</span>')
        xp_text = XPath('//text()')
        xp_b = XPath('.//b')
        xp_span_class = XPath('//span/@class')
        xp_desc_text = XPath('.//text()')
        # Text node
        x1 = r.xpath(xp_text)
        self.assertEquals(x1.extract(), [u'some text'])
        self.assertEquals(x1.xpath(xp_b).extract(), [])
        # Tag attribute
        x1 = r.xpath(xp_span_class)
        self.assertEquals(x1.extract(), [u'big'])
        self.assertEquals(x1.xpath(xp_desc_text).extract(), [])

    def test_select_on_text_nodes(self):
        xp1 = XPath("//div/descendant::text()[preceding-sibling::b[contains(text(), 'Options')]]")
        xp2 = XPath("//div/descendant::text()/preceding-sibling::b[contains(text(), 'Options')]")

        r = self.sscls(text=u'<div><b>Options:</b>opt1</div><div><b>Other</b>opt2</div>')

        x1 = r.xpath(xp1)
        self.assertEquals(x1.extract(), [u'opt1'])

        x1 = r.xpath(xp2)
        self.assertEquals(x1.extract(), [u'<b>Options:</b>'])

    def test_nested_select_on_text_nodes(self):
        xp1 = XPath("//div/descendant::text()")
        xp2 = XPath("./preceding-sibling::b[contains(text(), 'Options')]")
        # FIXME: does not work with lxml backend [upstream]
        r = self.sscls(text=u'<div><b>Options:</b>opt1</div><div><b>Other</b>opt2</div>')
        x1 = r.xpath(xp1)
        x2 = x1.xpath(xp2)
        self.assertEquals(x2.extract(), [u'<b>Options:</b>'])
    test_nested_select_on_text_nodes.skip = "Text nodes lost parent node reference in lxml"

    def test_weakref_slots(self):
        """Check that classes are using slots and are weak-referenceable"""
        x = self.sscls()
        weakref.ref(x)
        assert not hasattr(x, '__dict__'), "%s does not use __slots__" % \
            x.__class__.__name__

    def test_remove_namespaces(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-US" xmlns:media="http://search.yahoo.com/mrss/">
  <link type="text/html">
  <link type="application/atom+xml">
</feed>
"""
        xp_link = XPath("//link")
        sel = self.sscls(XmlResponse("http://example.com/feed.atom", body=xml))
        self.assertEqual(len(sel.xpath(xp_link)), 0)
        sel.remove_namespaces()
        self.assertEqual(len(sel.xpath(xp_link)), 2)

    def test_remove_attributes_namespaces(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:atom="http://www.w3.org/2005/Atom" xml:lang="en-US" xmlns:media="http://search.yahoo.com/mrss/">
  <link atom:type="text/html">
  <link atom:type="application/atom+xml">
</feed>
"""
        xp_link_type = XPath("//link/@type")
        sel = self.sscls(XmlResponse("http://example.com/feed.atom", body=xml))
        self.assertEqual(len(sel.xpath(xp_link_type)), 0)
        sel.remove_namespaces()
        self.assertEqual(len(sel.xpath(xp_link_type)), 2)


class DeprecatedXpathSelectorTest(unittest.TestCase):

    text = '<div><img src="a.jpg"><p>Hello</div>'

    def test_warnings(self):
        for cls in XPathSelector, HtmlXPathSelector, XPathSelector:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter('always')
                hs = cls(text=self.text)
                assert len(w) == 1, w
                assert issubclass(w[0].category, ScrapyDeprecationWarning)
                assert 'deprecated' in str(w[-1].message)
                hs.select("//div").extract()
                assert issubclass(w[1].category, ScrapyDeprecationWarning)
                assert 'deprecated' in str(w[-1].message)

    def test_xpathselector(self):
        with warnings.catch_warnings(record=True):
            hs = XPathSelector(text=self.text)
            self.assertEqual(hs.select("//div").extract(),
                             [u'<div><img src="a.jpg"><p>Hello</p></div>'])
            self.assertRaises(RuntimeError, hs.css, 'div')

    def test_htmlxpathselector(self):
        with warnings.catch_warnings(record=True):
            hs = HtmlXPathSelector(text=self.text)
            self.assertEqual(hs.select("//div").extract(),
                             [u'<div><img src="a.jpg"><p>Hello</p></div>'])
            self.assertRaises(RuntimeError, hs.css, 'div')

    def test_xmlxpathselector(self):
        with warnings.catch_warnings(record=True):
            xs = XmlXPathSelector(text=self.text)
            self.assertEqual(xs.select("//div").extract(),
                             [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])
            self.assertRaises(RuntimeError, xs.css, 'div')
