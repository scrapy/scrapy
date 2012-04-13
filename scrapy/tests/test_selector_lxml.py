"""
Selectors tests, specific for lxml backend
"""

import unittest
from scrapy.tests import test_selector
from scrapy.http import TextResponse, HtmlResponse
from scrapy.selector.lxmldocument import LxmlDocument
from scrapy.selector.lxmlsel import XmlXPathSelector, HtmlXPathSelector, XPathSelector


class LxmlXPathSelectorTestCase(test_selector.XPathSelectorTestCase):

    xs_cls = XPathSelector
    hxs_cls = HtmlXPathSelector
    xxs_cls = XmlXPathSelector


class Libxml2DocumentTest(unittest.TestCase):

    def test_caching(self):
        r1 = HtmlResponse('http://www.example.com', body='<html><head></head><body></body></html>')
        r2 = r1.copy()

        doc1 = LxmlDocument(r1)
        doc2 = LxmlDocument(r1)
        doc3 = LxmlDocument(r2)

        # make sure it's cached
        assert doc1 is doc2
        assert doc1 is not doc3

        # don't leave documents in memory to avoid wrong libxml2 leaks reports
        del doc1, doc2, doc3

    def test_null_char(self):
        # make sure bodies with null char ('\x00') don't raise a TypeError exception
        self.body_content = 'test problematic \x00 body'
        response = TextResponse('http://example.com/catalog/product/blabla-123',
                            headers={'Content-Type': 'text/plain; charset=utf-8'}, body=self.body_content)
        LxmlDocument(response)
