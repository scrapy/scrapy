import re
import unittest
from scrapy.contrib.linkextractors.regex import RegexLinkExtractor
from scrapy.http import HtmlResponse
from scrapy.link import Link
from scrapy.contrib.linkextractors.htmlparser import HtmlParserLinkExtractor
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor, BaseSgmlLinkExtractor
from scrapy.tests import get_testdata


class LinkExtractorTestCase(unittest.TestCase):
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

        self.assertEqual(lx.extract_links(response_latin1), [
            Link(url='http://example.com/sample_%F1.html', text=''),
            Link(url='http://example.com/sample_%E1.html', text='sample \xe1 text'.decode('latin1')),
        ])

    def test_matches(self):
        url1 = 'http://lotsofstuff.com/stuff1/index'
        url2 = 'http://evenmorestuff.com/uglystuff/index'

        lx = BaseSgmlLinkExtractor()
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), True)

    def test_link_nofollow(self):
        html = """
        <a href="page.html?action=print" rel="nofollow">Printer-friendly page</a>
        <a href="about.html">About us</a>
        """
        response = HtmlResponse("http://example.org/page.html", body=html)
        lx = SgmlLinkExtractor()
        self.assertEqual([link for link in lx.extract_links(response)], [
            Link(url='http://example.org/page.html?action=print', text=u'Printer-friendly page', nofollow=True),
            Link(url='http://example.org/about.html', text=u'About us', nofollow=False),
        ])


class SgmlLinkExtractorTestCase(unittest.TestCase):
    def setUp(self):
        body = get_testdata('link_extractor', 'sgml_linkextractor.html')
        self.response = HtmlResponse(url='http://example.com/index', body=body)

    def test_urls_type(self):
        '''Test that the resulting urls are regular strings and not a unicode objects'''
        lx = SgmlLinkExtractor()
        self.assertTrue(all(isinstance(link.url, str) for link in lx.extract_links(self.response)))

    def test_extraction(self):
        '''Test the extractor's behaviour among different situations'''

        lx = SgmlLinkExtractor()
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
            Link(url='http://www.google.com/something', text=u''),
            Link(url='http://example.com/innertag.html', text=u'inner tag'),
        ])

        lx = SgmlLinkExtractor(allow=('sample', ))
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
        ])

        lx = SgmlLinkExtractor(allow=('sample', ), unique=False)
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
            Link(url='http://example.com/sample3.html', text=u'sample 3 repetition'),
        ])

        lx = SgmlLinkExtractor(allow=('sample', ))
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
        ])

        lx = SgmlLinkExtractor(allow=('sample', ), deny=('3', ))
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
        ])

        lx = SgmlLinkExtractor(allow_domains=('google.com', ))
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://www.google.com/something', text=u''),
        ])

    def test_extraction_using_single_values(self):
        '''Test the extractor's behaviour among different situations'''

        lx = SgmlLinkExtractor(allow='sample')
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
        ])

        lx = SgmlLinkExtractor(allow='sample', deny='3')
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
        ])

        lx = SgmlLinkExtractor(allow_domains='google.com')
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://www.google.com/something', text=u''),
        ])

        lx = SgmlLinkExtractor(deny_domains='example.com')
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://www.google.com/something', text=u''),
        ])

    def test_matches(self):
        url1 = 'http://lotsofstuff.com/stuff1/index'
        url2 = 'http://evenmorestuff.com/uglystuff/index'

        lx = SgmlLinkExtractor(allow=(r'stuff1', ))
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), False)

        lx = SgmlLinkExtractor(deny=(r'uglystuff', ))
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), False)

        lx = SgmlLinkExtractor(allow_domains=('evenmorestuff.com', ))
        self.assertEqual(lx.matches(url1), False)
        self.assertEqual(lx.matches(url2), True)

        lx = SgmlLinkExtractor(deny_domains=('lotsofstuff.com', ))
        self.assertEqual(lx.matches(url1), False)
        self.assertEqual(lx.matches(url2), True)

        lx = SgmlLinkExtractor(allow=('blah1',), deny=('blah2',),
                               allow_domains=('blah1.com',),
                               deny_domains=('blah2.com',))
        self.assertEqual(lx.matches('http://blah1.com/blah1'), True)
        self.assertEqual(lx.matches('http://blah1.com/blah2'), False)
        self.assertEqual(lx.matches('http://blah2.com/blah1'), False)
        self.assertEqual(lx.matches('http://blah2.com/blah2'), False)

    def test_restrict_xpaths(self):
        lx = SgmlLinkExtractor(restrict_xpaths=('//div[@id="subwrapper"]', ))
        self.assertEqual([link for link in lx.extract_links(self.response)], [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
        ])

    def test_restrict_xpaths_encoding(self):
        """Test restrict_xpaths with encodings"""
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <div class='links'>
        <p><a href="/about.html">About us\xa3</a></p>
        </div>
        <div>
        <p><a href="/nofollow.html">This shouldn't be followed</a></p>
        </div>
        </body></html>"""
        response = HtmlResponse("http://example.org/somepage/index.html", body=html, encoding='windows-1252')

        lx = SgmlLinkExtractor(restrict_xpaths="//div[@class='links']")
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://example.org/about.html', text=u'About us\xa3')])

    def test_restrict_xpaths_with_html_entities(self):
        html = '<html><body><p><a href="/&hearts;/you?c=&euro;">text</a></p></body></html>'
        response = HtmlResponse("http://example.org/somepage/index.html", body=html, encoding='iso8859-15')
        links = SgmlLinkExtractor(restrict_xpaths='//p').extract_links(response)
        self.assertEqual(links,
                         [Link(url='http://example.org/%E2%99%A5/you?c=%E2%82%AC', text=u'text')])

    def test_restrict_xpaths_concat_in_handle_data(self):
        """html entities cause SGMLParser to call handle_data hook twice"""
        body = """<html><body><div><a href="/foo">&gt;\xbe\xa9&lt;\xb6\xab</a></body></html>"""
        response = HtmlResponse("http://example.org", body=body, encoding='gb18030')
        lx = SgmlLinkExtractor(restrict_xpaths="//div")
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://example.org/foo', text=u'>\u4eac<\u4e1c',
                               fragment='', nofollow=False)])

    def test_encoded_url(self):
        body = """<html><body><div><a href="?page=2">BinB</a></body></html>"""
        response = HtmlResponse("http://known.fm/AC%2FDC/", body=body, encoding='utf8')
        lx = SgmlLinkExtractor()
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://known.fm/AC%2FDC/?page=2', text=u'BinB', fragment='', nofollow=False),
        ])

    def test_encoded_url_in_restricted_xpath(self):
        body = """<html><body><div><a href="?page=2">BinB</a></body></html>"""
        response = HtmlResponse("http://known.fm/AC%2FDC/", body=body, encoding='utf8')
        lx = SgmlLinkExtractor(restrict_xpaths="//div")
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://known.fm/AC%2FDC/?page=2', text=u'BinB', fragment='', nofollow=False),
        ])

    def test_deny_extensions(self):
        html = """<a href="page.html">asd</a> and <a href="photo.jpg">"""
        response = HtmlResponse("http://example.org/", body=html)
        lx = SgmlLinkExtractor()
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.org/page.html', text=u'asd'),
        ])

        lx = SgmlLinkExtractor(deny_extensions="jpg")
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.org/page.html', text=u'asd'),
        ])

    def test_process_value(self):
        """Test restrict_xpaths with encodings"""
        html = """
        <a href="javascript:goToPage('../other/page.html','photo','width=600,height=540,scrollbars'); return false">Link text</a>
        <a href="/about.html">About us</a>
        """
        response = HtmlResponse("http://example.org/somepage/index.html", body=html, encoding='windows-1252')

        def process_value(value):
            m = re.search("javascript:goToPage\('(.*?)'", value)
            if m:
                return m.group(1)

        lx = SgmlLinkExtractor(process_value=process_value)
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://example.org/other/page.html', text='Link text')])

    def test_base_url_with_restrict_xpaths(self):
        html = """<html><head><title>Page title<title><base href="http://otherdomain.com/base/" />
        <body><p><a href="item/12.html">Item 12</a></p>
        </body></html>"""
        response = HtmlResponse("http://example.org/somepage/index.html", body=html)
        lx = SgmlLinkExtractor(restrict_xpaths="//p")
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://otherdomain.com/base/item/12.html', text='Item 12')])


    def test_attrs(self):
        lx = SgmlLinkExtractor(attrs="href")
        self.assertEqual(lx.extract_links(self.response), [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
            Link(url='http://www.google.com/something', text=u''),
            Link(url='http://example.com/innertag.html', text=u'inner tag'),
        ])

        lx = SgmlLinkExtractor(attrs=("href","src"), tags=("a","area","img"), deny_extensions=())
        self.assertEqual(lx.extract_links(self.response), [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample2.jpg', text=u''),
            Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
            Link(url='http://www.google.com/something', text=u''),
            Link(url='http://example.com/innertag.html', text=u'inner tag'),
        ])

        lx = SgmlLinkExtractor(attrs=None)
        self.assertEqual(lx.extract_links(self.response), [])

        html = """<html><area href="sample1.html"></area><a ref="sample2.html">sample text 2</a></html>"""
        response = HtmlResponse("http://example.com/index.html", body=html)
        lx = SgmlLinkExtractor(attrs=("href"))
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.com/sample1.html', text=u''),
        ])


    def test_tags(self):
        html = """<html><area href="sample1.html"></area><a href="sample2.html">sample 2</a><img src="sample2.jpg"/></html>"""
        response = HtmlResponse("http://example.com/index.html", body=html)

        lx = SgmlLinkExtractor(tags=None)
        self.assertEqual(lx.extract_links(response), [])

        lx = SgmlLinkExtractor()
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.com/sample1.html', text=u''),
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
        ])

        lx = SgmlLinkExtractor(tags="area")
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.com/sample1.html', text=u''),
        ])

        lx = SgmlLinkExtractor(tags="a")
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
        ])

        lx = SgmlLinkExtractor(tags=("a","img"), attrs=("href", "src"), deny_extensions=())
        self.assertEqual(lx.extract_links(response), [
            Link(url='http://example.com/sample2.html', text=u'sample 2'),
            Link(url='http://example.com/sample2.jpg', text=u''),
        ])


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


class RegexLinkExtractorTestCase(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
