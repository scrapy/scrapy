import warnings
import weakref
from twisted.trial import unittest
from scrapy.http import TextResponse, HtmlResponse, XmlResponse
from scrapy.selector import Selector
from scrapy.selector.lxmlsel import XmlXPathSelector, HtmlXPathSelector, XPathSelector
from lxml import etree


class SelectorTestCase(unittest.TestCase):

    def test_simple_selection(self):
        """Simple selector tests"""
        body = b"<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body, encoding='utf-8')
        sel = Selector(response)

        xl = sel.xpath('//input')
        self.assertEqual(2, len(xl))
        for x in xl:
            assert isinstance(x, Selector)

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

    def test_root_base_url(self):
        body = b'<html><form action="/path"><input name="a" /></form></html>'
        url = "http://example.com"
        response = TextResponse(url=url, body=body, encoding='utf-8')
        sel = Selector(response)
        self.assertEqual(url, sel.root.base)

    def test_deprecated_root_argument(self):
        with warnings.catch_warnings(record=True) as w:
            root = etree.fromstring(u'<html/>')
            sel = Selector(_root=root)
            self.assertIs(root, sel.root)
            self.assertEqual(str(w[-1].message),
                             'Argument `_root` is deprecated, use `root` instead')

    def test_deprecated_root_argument_ambiguous(self):
        with warnings.catch_warnings(record=True) as w:
            _root = etree.fromstring(u'<xml/>')
            root = etree.fromstring(u'<html/>')
            sel = Selector(_root=_root, root=root)
            self.assertIs(root, sel.root)
            self.assertIn('Ignoring deprecated `_root` argument', str(w[-1].message))

    def test_flavor_detection(self):
        text = b'<div><img src="a.jpg"><p>Hello</div>'
        sel = Selector(XmlResponse('http://example.com', body=text, encoding='utf-8'))
        self.assertEqual(sel.type, 'xml')
        self.assertEqual(sel.xpath("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></img></div>'])

        sel = Selector(HtmlResponse('http://example.com', body=text, encoding='utf-8'))
        self.assertEqual(sel.type, 'html')
        self.assertEqual(sel.xpath("//div").extract(),
                         [u'<div><img src="a.jpg"><p>Hello</p></div>'])

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
        x = Selector(response)
        self.assertEquals(x.xpath("//span[@id='blank']/text()").extract(),
                          [u'\xa3'])

    def test_badly_encoded_body(self):
        # \xe9 alone isn't valid utf8 sequence
        r1 = TextResponse('http://www.example.com', \
                          body=b'<html><p>an Jos\xe9 de</p><html>', \
                          encoding='utf-8')
        Selector(r1).xpath('//text()').extract()

    def test_weakref_slots(self):
        """Check that classes are using slots and are weak-referenceable"""
        x = Selector(text='')
        weakref.ref(x)
        assert not hasattr(x, '__dict__'), "%s does not use __slots__" % \
            x.__class__.__name__

    def test_deprecated_selector_methods(self):
        sel = Selector(TextResponse(url="http://example.com", body=b'<p>some text</p>'))

        with warnings.catch_warnings(record=True) as w:
            sel.select('//p')
            self.assertSubstring('Use .xpath() instead', str(w[-1].message))

        with warnings.catch_warnings(record=True) as w:
            sel.extract_unquoted()
            self.assertSubstring('Use .extract() instead', str(w[-1].message))

    def test_deprecated_selectorlist_methods(self):
        sel = Selector(TextResponse(url="http://example.com", body=b'<p>some text</p>'))

        with warnings.catch_warnings(record=True) as w:
            sel.xpath('//p').select('.')
            self.assertSubstring('Use .xpath() instead', str(w[-1].message))

        with warnings.catch_warnings(record=True) as w:
            sel.xpath('//p').extract_unquoted()
            self.assertSubstring('Use .extract() instead', str(w[-1].message))

    def test_selector_bad_args(self):
        with self.assertRaisesRegexp(ValueError, 'received both response and text'):
            Selector(TextResponse(url='http://example.com', body=b''), text=u'')


class DeprecatedXpathSelectorTest(unittest.TestCase):

    text = '<div><img src="a.jpg"><p>Hello</div>'

    def test_warnings_xpathselector(self):
        cls = XPathSelector
        with warnings.catch_warnings(record=True) as w:
            class UserClass(cls):
                pass

            # subclassing must issue a warning
            self.assertEqual(len(w), 1, str(cls))
            self.assertIn('scrapy.Selector', str(w[0].message))

            # subclass instance doesn't issue a warning
            usel = UserClass(text=self.text)
            self.assertEqual(len(w), 1)

            # class instance must issue a warning
            sel = cls(text=self.text)
            self.assertEqual(len(w), 2, str((cls, [x.message for x in w])))
            self.assertIn('scrapy.Selector', str(w[1].message))

            # subclass and instance checks
            self.assertTrue(issubclass(cls, Selector))
            self.assertTrue(isinstance(sel, Selector))
            self.assertTrue(isinstance(usel, Selector))

    def test_warnings_xmlxpathselector(self):
        cls = XmlXPathSelector
        with warnings.catch_warnings(record=True) as w:
            class UserClass(cls):
                pass

            # subclassing must issue a warning
            self.assertEqual(len(w), 1, str(cls))
            self.assertIn('scrapy.Selector', str(w[0].message))

            # subclass instance doesn't issue a warning
            usel = UserClass(text=self.text)
            self.assertEqual(len(w), 1)

            # class instance must issue a warning
            sel = cls(text=self.text)
            self.assertEqual(len(w), 2, str((cls, [x.message for x in w])))
            self.assertIn('scrapy.Selector', str(w[1].message))

            # subclass and instance checks
            self.assertTrue(issubclass(cls, Selector))
            self.assertTrue(issubclass(cls, XPathSelector))
            self.assertTrue(isinstance(sel, Selector))
            self.assertTrue(isinstance(usel, Selector))
            self.assertTrue(isinstance(sel, XPathSelector))
            self.assertTrue(isinstance(usel, XPathSelector))

    def test_warnings_htmlxpathselector(self):
        cls = HtmlXPathSelector
        with warnings.catch_warnings(record=True) as w:
            class UserClass(cls):
                pass

            # subclassing must issue a warning
            self.assertEqual(len(w), 1, str(cls))
            self.assertIn('scrapy.Selector', str(w[0].message))

            # subclass instance doesn't issue a warning
            usel = UserClass(text=self.text)
            self.assertEqual(len(w), 1)

            # class instance must issue a warning
            sel = cls(text=self.text)
            self.assertEqual(len(w), 2, str((cls, [x.message for x in w])))
            self.assertIn('scrapy.Selector', str(w[1].message))

            # subclass and instance checks
            self.assertTrue(issubclass(cls, Selector))
            self.assertTrue(issubclass(cls, XPathSelector))
            self.assertTrue(isinstance(sel, Selector))
            self.assertTrue(isinstance(usel, Selector))
            self.assertTrue(isinstance(sel, XPathSelector))
            self.assertTrue(isinstance(usel, XPathSelector))
