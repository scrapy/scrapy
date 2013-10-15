"""
Selector tests for cssselect backend
"""
from twisted.trial import unittest
from scrapy.http import HtmlResponse
from scrapy.selector.csstranslator import ScrapyHTMLTranslator
from scrapy.selector import Selector
from cssselect.parser import SelectorSyntaxError
from cssselect.xpath import ExpressionError


HTMLBODY = '''
<html>
<body>
<div>
 <a id="name-anchor" name="foo"></a>
 <a id="tag-anchor" rel="tag" href="http://localhost/foo">link</a>
 <a id="nofollow-anchor" rel="nofollow" href="https://example.org"> link</a>
 <p id="paragraph">
   lorem ipsum text
   <b id="p-b">hi</b> <em id="p-em">there</em>
   <b id="p-b2">guy</b>
   <input type="checkbox" id="checkbox-unchecked" />
   <input type="checkbox" id="checkbox-disabled" disabled="" />
   <input type="text" id="text-checked" checked="checked" />
   <input type="hidden" />
   <input type="hidden" disabled="disabled" />
   <input type="checkbox" id="checkbox-checked" checked="checked" />
   <input type="checkbox" id="checkbox-disabled-checked"
          disabled="disabled" checked="checked" />
   <fieldset id="fieldset" disabled="disabled">
     <input type="checkbox" id="checkbox-fieldset-disabled" />
     <input type="hidden" />
   </fieldset>
 </p>
 <map name="dummymap">
   <area shape="circle" coords="200,250,25" href="foo.html" id="area-href" />
   <area shape="default" id="area-nohref" />
 </map>
</div>
<div class="cool-footer" id="foobar-div" foobar="ab bc cde">
    <span id="foobar-span">foo ter</span>
</div>
</body></html>
'''


class TranslatorMixinTest(unittest.TestCase):

    tr_cls = ScrapyHTMLTranslator

    def setUp(self):
        self.tr = self.tr_cls()
        self.c2x = self.tr.css_to_xpath

    def test_attr_function(self):
        cases = [
            ('::attr(name)', u'descendant-or-self::*/@name'),
            ('a::attr(href)', u'descendant-or-self::a/@href'),
            ('a ::attr(img)', u'descendant-or-self::a/descendant-or-self::*/@img'),
            ('a > ::attr(class)', u'descendant-or-self::a/*/@class'),
        ]
        for css, xpath in cases:
            self.assertEqual(self.c2x(css), xpath, css)

    def test_attr_function_exception(self):
        cases = [
            ('::attr(12)', ExpressionError),
            ('::attr(34test)', ExpressionError),
            ('::attr(@href)', SelectorSyntaxError),
        ]
        for css, exc in cases:
            self.assertRaises(exc, self.c2x, css)

    def test_text_pseudo_element(self):
        cases = [
            ('::text', u'descendant-or-self::text()'),
            ('p::text', u'descendant-or-self::p/text()'),
            ('p ::text', u'descendant-or-self::p/descendant-or-self::text()'),
            ('#id::text', u"descendant-or-self::*[@id = 'id']/text()"),
            ('p#id::text', u"descendant-or-self::p[@id = 'id']/text()"),
            ('p#id ::text', u"descendant-or-self::p[@id = 'id']/descendant-or-self::text()"),
            ('p#id > ::text', u"descendant-or-self::p[@id = 'id']/*/text()"),
            ('p#id ~ ::text', u"descendant-or-self::p[@id = 'id']/following-sibling::*/text()"),
            ('a[href]::text', u'descendant-or-self::a[@href]/text()'),
            ('a[href] ::text', u'descendant-or-self::a[@href]/descendant-or-self::text()'),
            ('p::text, a::text', u"descendant-or-self::p/text() | descendant-or-self::a/text()"),
        ]
        for css, xpath in cases:
            self.assertEqual(self.c2x(css), xpath, css)

    def test_pseudo_function_exception(self):
        cases = [
            ('::attribute(12)', ExpressionError),
            ('::text()', ExpressionError),
            ('::attr(@href)', SelectorSyntaxError),
        ]
        for css, exc in cases:
            self.assertRaises(exc, self.c2x, css)

    def test_unknown_pseudo_element(self):
        cases = [
            ('::text-node', ExpressionError),
        ]
        for css, exc in cases:
            self.assertRaises(exc, self.c2x, css)

    def test_unknown_pseudo_class(self):
        cases = [
            (':text', ExpressionError),
            (':attribute(name)', ExpressionError),
        ]
        for css, exc in cases:
            self.assertRaises(exc, self.c2x, css)


class CSSSelectorTest(unittest.TestCase):

    sscls = Selector

    def setUp(self):
        self.htmlresponse = HtmlResponse('http://example.com', body=HTMLBODY)
        self.sel = self.sscls(self.htmlresponse)

    def x(self, *a, **kw):
        return [v.strip() for v in self.sel.css(*a, **kw).extract() if v.strip()]

    def test_selector_simple(self):
        for x in self.sel.css('input'):
            self.assertTrue(isinstance(x, self.sel.__class__), x)
        self.assertEqual(self.sel.css('input').extract(),
                         [x.extract() for x in self.sel.css('input')])

    def test_text_pseudo_element(self):
        self.assertEqual(self.x('#p-b2'), [u'<b id="p-b2">guy</b>'])
        self.assertEqual(self.x('#p-b2::text'), [u'guy'])
        self.assertEqual(self.x('#p-b2 ::text'), [u'guy'])
        self.assertEqual(self.x('#paragraph::text'), [u'lorem ipsum text'])
        self.assertEqual(self.x('#paragraph ::text'), [u'lorem ipsum text', u'hi', u'there', u'guy'])
        self.assertEqual(self.x('p::text'), [u'lorem ipsum text'])
        self.assertEqual(self.x('p ::text'), [u'lorem ipsum text', u'hi', u'there', u'guy'])

    def test_attribute_function(self):
        self.assertEqual(self.x('#p-b2::attr(id)'), [u'p-b2'])
        self.assertEqual(self.x('.cool-footer::attr(class)'), [u'cool-footer'])
        self.assertEqual(self.x('.cool-footer ::attr(id)'), [u'foobar-div', u'foobar-span'])
        self.assertEqual(self.x('map[name="dummymap"] ::attr(shape)'), [u'circle', u'default'])

    def test_nested_selector(self):
        self.assertEqual(self.sel.css('p').css('b::text').extract(),
                         [u'hi', u'guy'])
        self.assertEqual(self.sel.css('div').css('area:last-child').extract(),
                         [u'<area shape="default" id="area-nohref">'])
