"""
Selectors tests, specific for libxml2 backend
"""

from twisted.trial import unittest
from scrapy import optional_features


from scrapy.http import TextResponse, HtmlResponse, XmlResponse
from scrapy.selector.libxml2sel import XmlXPathSelector, HtmlXPathSelector, \
    XPathSelector
from scrapy.selector.libxml2document import Libxml2Document
from scrapy.utils.test import libxml2debug
from scrapy.tests import test_selector


class Libxml2XPathSelectorTestCase(test_selector.XPathSelectorTestCase):

    xs_cls = XPathSelector
    hxs_cls = HtmlXPathSelector
    xxs_cls = XmlXPathSelector

    skip = 'libxml2' not in optional_features

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

        self.assertEqual(xxs.select('/root').extract_unquoted(), [u''])
        self.assertEqual(xxs.select('/root/text()').extract_unquoted(), [
            u'\n  lala\n  ',
            u'\n  pff\n'])

        self.assertEqual(xxs.select('//*').extract_unquoted(), [u'', u'', u''])
        self.assertEqual(xxs.select('//text()').extract_unquoted(), [
            u'\n  lala\n  ',
            u'\n    blabla&more',
            u'a',
            u'test',
            u'oh\n    ',
            u'lalalal&ppppp<b>PPPP</b>ppp&amp;la',
            u'\n  ',
            u'\n  pff\n'])


class Libxml2DocumentTest(unittest.TestCase):

    skip = 'libxml2' not in optional_features

    @libxml2debug
    def test_response_libxml2_caching(self):
        r1 = HtmlResponse('http://www.example.com', body='<html><head></head><body></body></html>')
        r2 = r1.copy()

        doc1 = Libxml2Document(r1)
        doc2 = Libxml2Document(r1)
        doc3 = Libxml2Document(r2)

        # make sure it's cached
        assert doc1 is doc2
        assert doc1.xmlDoc is doc2.xmlDoc
        assert doc1 is not doc3
        assert doc1.xmlDoc is not doc3.xmlDoc

        # don't leave libxml2 documents in memory to avoid wrong libxml2 leaks reports
        del doc1, doc2, doc3

    @libxml2debug
    def test_null_char(self):
        # make sure bodies with null char ('\x00') don't raise a TypeError exception
        self.body_content = 'test problematic \x00 body'
        response = TextResponse('http://example.com/catalog/product/blabla-123',
                            headers={'Content-Type': 'text/plain; charset=utf-8'}, body=self.body_content)
        Libxml2Document(response)

if __name__ == "__main__":
    unittest.main()
