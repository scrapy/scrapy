"""
Selectors tests, specific for lxml backend
"""

import unittest
from scrapy.tests import test_selector
from scrapy.http import TextResponse, HtmlResponse, XmlResponse
from scrapy.selector.lxmldocument import LxmlDocument
from scrapy.selector.lxmlsel import XmlXPathSelector, HtmlXPathSelector, XPathSelector


class LxmlXPathSelectorTestCase(test_selector.XPathSelectorTestCase):

    xs_cls = XPathSelector
    hxs_cls = HtmlXPathSelector
    xxs_cls = XmlXPathSelector

    def test_remove_namespaces(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-US" xmlns:media="http://search.yahoo.com/mrss/">
  <link type="text/html">
  <link type="application/atom+xml">
</feed>
"""
        xxs = XmlXPathSelector(XmlResponse("http://example.com/feed.atom", body=xml))
        self.assertEqual(len(xxs.select("//link")), 0)
        xxs.remove_namespaces()
        self.assertEqual(len(xxs.select("//link")), 2)

    def test_remove_attributes_namespaces(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:atom="http://www.w3.org/2005/Atom" xml:lang="en-US" xmlns:media="http://search.yahoo.com/mrss/">
  <link atom:type="text/html">
  <link atom:type="application/atom+xml">
</feed>
"""
        xxs = XmlXPathSelector(XmlResponse("http://example.com/feed.atom", body=xml))
        self.assertEqual(len(xxs.select("//link/@type")), 0)
        xxs.remove_namespaces()
        self.assertEqual(len(xxs.select("//link/@type")), 2)

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
