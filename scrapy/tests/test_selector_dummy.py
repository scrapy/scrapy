import unittest

from scrapy.http import TextResponse
from scrapy.selector.dummysel import XmlXPathSelector, HtmlXPathSelector, \
    XPathSelector

class XPathSelectorTestCase(unittest.TestCase):

    def test_raises(self):
        response = TextResponse(url="http://example.com", body='test')
        for cls in [XmlXPathSelector, HtmlXPathSelector, XPathSelector]:
            sel = cls(response)
            self.assertRaises(RuntimeError, sel.select, '//h2')
            self.assertRaises(RuntimeError, sel.re, 'lala')
            self.assertRaises(RuntimeError, sel.extract)
            self.assertRaises(RuntimeError, sel.register_namespace, 'a', 'b')
            self.assertRaises(RuntimeError, sel.__nonzero__, 'a', 'b')
