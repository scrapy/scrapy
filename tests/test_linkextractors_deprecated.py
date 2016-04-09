# -*- coding: utf-8 -*-
import unittest
from scrapy.linkextractors.regex import RegexLinkExtractor
from scrapy.http import HtmlResponse
from scrapy.link import Link
from scrapy.linkextractors.htmlparser import HtmlParserLinkExtractor
from scrapy.linkextractors.sgml import SgmlLinkExtractor, BaseSgmlLinkExtractor
from tests import get_testdata

from tests.test_linkextractors import Base


class BaseSgmlLinkExtractorTestCase(unittest.TestCase):
    # XXX: should we move some of these tests to base link extractor tests?

    def test_basic(self):
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/">&gt;&gt;</a></p>
        <p><a href="/" /></p>
        </body></html>"""
        response = HtmlResponse("http://example.org/somepage/index.html", body=html)

        lx = BaseSgmlLinkExtractor()  # default: tag=a, attr=href
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://example.org/somepage/item/12.html', text='Item 12'),
                          Link(url='http://example.org/about.html', text='About us'),
                          Link(url='http://example.org/othercat.html', text='Other category'),
                          Link(url='http://example.org/', text='>>'),
                          Link(url='http://example.org/', text='')])

    def test_base_url(self):
        html = """<html><head><title>Page title<title><base href="http://otherdomain.com/base/" />
        <body><p><a href="item/12.html">Item 12</a></p>
        </body></html>"""
        response = HtmlResponse("http://example.org/somepage/index.html", body=html)

        lx = BaseSgmlLinkExtractor()  # default: tag=a, attr=href
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://otherdomain.com/base/item/12.html', text='Item 12')])

        # base url is an absolute path and relative to host
        html = """<html><head><title>Page title<title><base href="/" />
        <body><p><a href="item/12.html">Item 12</a></p></body></html>"""
        response = HtmlResponse("https://example.org/somepage/index.html", body=html)
        self.assertEqual(lx.extract_links(response),
                         [Link(url='https://example.org/item/12.html', text='Item 12')])

        # base url has no scheme
        html = """<html><head><title>Page title<title><base href="//noschemedomain.com/path/to/" />
        <body><p><a href="item/12.html">Item 12</a></p></body></html>"""
        response = HtmlResponse("https://example.org/somepage/index.html", body=html)
        self.assertEqual(lx.extract_links(response),
                         [Link(url='https://noschemedomain.com/path/to/item/12.html', text='Item 12')])

    def test_link_text_wrong_encoding(self):
        html = """<body><p><a href="item/12.html">Wrong: \xed</a></p></body></html>"""
        response = HtmlResponse("http://www.example.com", body=html, encoding='utf-8')
        lx = BaseSgmlLinkExtractor()
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://www.example.com/item/12.html', text=u'Wrong: \ufffd'),
        ])

    def test_extraction_encoding(self):
        body = get_testdata('link_extractor', 'linkextractor_noenc.html')
        response_utf8 = HtmlResponse(url='http://example.com/utf8', body=body, headers={'Content-Type': ['text/html; charset=utf-8']})
        response_noenc = HtmlResponse(url='http://example.com/noenc', body=body)
        body = get_testdata('link_extractor', 'linkextractor_latin1.html')
        response_latin1 = HtmlResponse(url='http://example.com/latin1', body=body)

        lx = BaseSgmlLinkExtractor()
        self.assertEqual(lx.extract_links(response_utf8), [
            Link(url='http://example.com/sample_%C3%B1.html', text=''),
            Link(url='http://example.com/sample_%E2%82%AC.html', text='sample \xe2\x82\xac text'.decode('utf-8')),
        ])

        self.assertEqual(lx.extract_links(response_noenc), [
            Link(url='http://example.com/sample_%C3%B1.html', text=''),
            Link(url='http://example.com/sample_%E2%82%AC.html', text='sample \xe2\x82\xac text'.decode('utf-8')),
        ])

        # document encoding does not affect URL path component, only query part
        # >>> u'sample_ñ.html'.encode('utf8')
        # b'sample_\xc3\xb1.html'
        # >>> u"sample_á.html".encode('utf8')
        # b'sample_\xc3\xa1.html'
        # >>> u"sample_ö.html".encode('utf8')
        # b'sample_\xc3\xb6.html'
        # >>> u"£32".encode('latin1')
        # b'\xa332'
        # >>> u"µ".encode('latin1')
        # b'\xb5'
        self.assertEqual(lx.extract_links(response_latin1), [
            Link(url='http://example.com/sample_%C3%B1.html', text=''),
            Link(url='http://example.com/sample_%C3%A1.html', text='sample \xe1 text'.decode('latin1')),
            Link(url='http://example.com/sample_%C3%B6.html?price=%A332&%B5=unit', text=''),
        ])

    def test_matches(self):
        url1 = 'http://lotsofstuff.com/stuff1/index'
        url2 = 'http://evenmorestuff.com/uglystuff/index'

        lx = BaseSgmlLinkExtractor()
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), True)


class HtmlParserLinkExtractorTestCase(unittest.TestCase):

    def setUp(self):
        body = get_testdata('link_extractor', 'sgml_linkextractor.html')
        self.response = HtmlResponse(url='http://example.com/index', body=body)

    def test_extraction(self):
        # Default arguments
        lx = HtmlParserLinkExtractor()
        self.assertEqual(lx.extract_links(self.response),
                         [Link(url='http://example.com/sample2.html', text=u'sample 2'),
                          Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
                          Link(url='http://example.com/sample3.html', text=u'sample 3 repetition'),
                          Link(url='http://www.google.com/something', text=u''),
                          Link(url='http://example.com/innertag.html', text=u'inner tag'),])

    def test_link_wrong_href(self):
        html = """
        <a href="http://example.org/item1.html">Item 1</a>
        <a href="http://[example.org/item2.html">Item 2</a>
        <a href="http://example.org/item3.html">Item 3</a>
        """
        response = HtmlResponse("http://example.org/index.html", body=html)
        lx = HtmlParserLinkExtractor()
        self.assertEqual([link for link in lx.extract_links(response)], [
            Link(url='http://example.org/item1.html', text=u'Item 1', nofollow=False),
            Link(url='http://example.org/item3.html', text=u'Item 3', nofollow=False),
        ])


class SgmlLinkExtractorTestCase(Base.LinkExtractorTestCase):
    extractor_cls = SgmlLinkExtractor

    def test_deny_extensions(self):
        html = """<a href="page.html">asd</a> and <a href="photo.jpg">"""
        response = HtmlResponse("http://example.org/", body=html)
        lx = SgmlLinkExtractor(deny_extensions="jpg")
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.org/page.html', text=u'asd'),
        ])

    def test_attrs_sgml(self):
        html = """<html><area href="sample1.html"></area>
        <a ref="sample2.html">sample text 2</a></html>"""
        response = HtmlResponse("http://example.com/index.html", body=html)
        lx = SgmlLinkExtractor(attrs="href")
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.com/sample1.html', text=u''),
        ])

    def test_link_nofollow(self):
        html = """
        <a href="page.html?action=print" rel="nofollow">Printer-friendly page</a>
        <a href="about.html">About us</a>
        <a href="http://google.com/something" rel="external nofollow">Something</a>
        """
        response = HtmlResponse("http://example.org/page.html", body=html)
        lx = SgmlLinkExtractor()
        self.assertEqual([link for link in lx.extract_links(response)], [
            Link(url='http://example.org/page.html?action=print', text=u'Printer-friendly page', nofollow=True),
            Link(url='http://example.org/about.html', text=u'About us', nofollow=False),
            Link(url='http://google.com/something', text=u'Something', nofollow=True),
        ])


class RegexLinkExtractorTestCase(unittest.TestCase):
    # XXX: RegexLinkExtractor is not deprecated yet, but it must be rewritten
    # not to depend on SgmlLinkExractor. Its speed is also much worse
    # than it should be.

    def setUp(self):
        body = get_testdata('link_extractor', 'sgml_linkextractor.html')
        self.response = HtmlResponse(url='http://example.com/index', body=body)

    def test_extraction(self):
        # Default arguments
        lx = RegexLinkExtractor()
        self.assertEqual(lx.extract_links(self.response),
                         [Link(url='http://example.com/sample2.html', text=u'sample 2'),
                          Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
                          Link(url='http://www.google.com/something', text=u''),
                          Link(url='http://example.com/innertag.html', text=u'inner tag'),])

    def test_link_wrong_href(self):
        html = """
        <a href="http://example.org/item1.html">Item 1</a>
        <a href="http://[example.org/item2.html">Item 2</a>
        <a href="http://example.org/item3.html">Item 3</a>
        """
        response = HtmlResponse("http://example.org/index.html", body=html)
        lx = RegexLinkExtractor()
        self.assertEqual([link for link in lx.extract_links(response)], [
            Link(url='http://example.org/item1.html', text=u'Item 1', nofollow=False),
            Link(url='http://example.org/item3.html', text=u'Item 3', nofollow=False),
        ])

    def test_html_base_href(self):
        html = """
        <html>
            <head>
                <base href="http://b.com/">
            </head>
            <body>
                <a href="test.html"></a>
            </body>
        </html>
        """
        response = HtmlResponse("http://a.com/", body=html)
        lx = RegexLinkExtractor()
        self.assertEqual([link for link in lx.extract_links(response)], [
            Link(url='http://b.com/test.html', text=u'', nofollow=False),
        ])
