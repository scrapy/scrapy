import os
import unittest

from scrapy.http import HtmlResponse
from scrapy.link import LinkExtractor, Link
from scrapy.link.extractors import RegexLinkExtractor
from scrapy.contrib.link_extractors import HTMLImageLinkExtractor

class LinkExtractorTestCase(unittest.TestCase):
    def test_basic(self):
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/" /></p>
        </body></html>"""
        response = HtmlResponse("http://example.org/somepage/index.html", body=html)

        lx = LinkExtractor()  # default: tag=a, attr=href
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://example.org/somepage/item/12.html', text='Item 12'), 
                          Link(url='http://example.org/about.html', text='About us'),
                          Link(url='http://example.org/othercat.html', text='Other category'), 
                          Link(url='http://example.org/', text='')])

    def test_base_url(self):
        html = """<html><head><title>Page title<title><base href="http://otherdomain.com/base/" />
        <body><p><a href="item/12.html">Item 12</a></p>
        </body></html>"""
        response = HtmlResponse("http://example.org/somepage/index.html", body=html)

        lx = LinkExtractor()  # default: tag=a, attr=href
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://otherdomain.com/base/item/12.html', text='Item 12')])

    def test_extraction_encoding(self):
        base_path = os.path.join(os.path.dirname(__file__), 'sample_data', 'link_extractor')
        body = open(os.path.join(base_path, 'linkextractor_noenc.html'), 'r').read()
        response_utf8 = HtmlResponse(url='http://example.com/utf8', body=body, headers={'Content-Type': ['text/html; charset=utf-8']})
        response_noenc = HtmlResponse(url='http://example.com/noenc', body=body)
        body = open(os.path.join(base_path, 'linkextractor_latin1.html'), 'r').read()
        response_latin1 = HtmlResponse(url='http://example.com/latin1', body=body)

        lx = LinkExtractor()
        self.assertEqual(lx.extract_links(response_utf8),
            [ Link(url='http://example.com/sample_%C3%B1.html', text=''),
              Link(url='http://example.com/sample_%E2%82%AC.html', text='sample \xe2\x82\xac text'.decode('utf-8')) ])

        self.assertEqual(lx.extract_links(response_noenc),
            [ Link(url='http://example.com/sample_%C3%B1.html', text=''),
              Link(url='http://example.com/sample_%E2%82%AC.html', text='sample \xe2\x82\xac text'.decode('utf-8')) ])

        self.assertEqual(lx.extract_links(response_latin1),
            [ Link(url='http://example.com/sample_%F1.html', text=''),
              Link(url='http://example.com/sample_%E1.html', text='sample \xe1 text'.decode('latin1')) ])

    def test_matches(self):
        url1 = 'http://lotsofstuff.com/stuff1/index'
        url2 = 'http://evenmorestuff.com/uglystuff/index'

        lx = LinkExtractor()
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), True)

class RegexLinkExtractorTestCase(unittest.TestCase):
    def setUp(self):
        base_path = os.path.join(os.path.dirname(__file__), 'sample_data', 'link_extractor')
        body = open(os.path.join(base_path, 'regex_linkextractor.html'), 'r').read()
        self.response = HtmlResponse(url='http://example.com/index', body=body)

    def test_urls_type(self):
        '''Test that the resulting urls are regular strings and not a unicode objects'''
        lx = RegexLinkExtractor()
        self.assertTrue(all(isinstance(link.url, str) for link in lx.extract_links(self.response)))

    def test_extraction(self):
        '''Test the extractor's behaviour among different situations'''

        lx = RegexLinkExtractor()
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample1.html', text=u''),
              Link(url='http://example.com/sample2.html', text=u'sample 2'),
              Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
              Link(url='http://www.google.com/something', text=u'') ])

        lx = RegexLinkExtractor(allow=('sample', ))
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample1.html', text=u''),
              Link(url='http://example.com/sample2.html', text=u'sample 2'),
              Link(url='http://example.com/sample3.html', text=u'sample 3 text') ])

        lx = RegexLinkExtractor(allow=('sample', ), unique=False)
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample1.html', text=u''),
              Link(url='http://example.com/sample2.html', text=u'sample 2'),
              Link(url='http://example.com/sample3.html', text=u'sample 3 text'),
              Link(url='http://example.com/sample3.html', text=u'sample 3 repetition') ])

        lx = RegexLinkExtractor(allow=('sample', ), deny=('3', ))
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample1.html', text=u''),
              Link(url='http://example.com/sample2.html', text=u'sample 2') ])

        lx = RegexLinkExtractor(allow_domains=('google.com', ))
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://www.google.com/something', text=u'') ])

        lx = RegexLinkExtractor(tags=('img', ), attrs=('src', ))
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample2.jpg', text=u'') ])

    def test_extraction_using_single_values(self):
        '''Test the extractor's behaviour among different situations'''

        lx = RegexLinkExtractor(allow='sample')
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample1.html', text=u''),
              Link(url='http://example.com/sample2.html', text=u'sample 2'),
              Link(url='http://example.com/sample3.html', text=u'sample 3 text') ])

        lx = RegexLinkExtractor(allow='sample', deny='3')
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample1.html', text=u''),
              Link(url='http://example.com/sample2.html', text=u'sample 2') ])

        lx = RegexLinkExtractor(allow_domains='google.com')
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://www.google.com/something', text=u'') ])

        lx = RegexLinkExtractor(deny_domains='example.com')
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://www.google.com/something', text=u'') ])

    def test_matches(self):
        url1 = 'http://lotsofstuff.com/stuff1/index'
        url2 = 'http://evenmorestuff.com/uglystuff/index'

        lx = RegexLinkExtractor(allow=(r'stuff1', ))
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), False)

        lx = RegexLinkExtractor(deny=(r'uglystuff', ))
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), False)

        lx = RegexLinkExtractor(allow_domains=('evenmorestuff.com', ))
        self.assertEqual(lx.matches(url1), False)
        self.assertEqual(lx.matches(url2), True)

        lx = RegexLinkExtractor(deny_domains=('lotsofstuff.com', ))
        self.assertEqual(lx.matches(url1), False)
        self.assertEqual(lx.matches(url2), True)

        lx = RegexLinkExtractor(allow=('blah1', ), deny=('blah2', ),
            allow_domains=('blah1.com', ), deny_domains=('blah2.com', ))
        self.assertEqual(lx.matches('http://blah1.com/blah1'), True)
        self.assertEqual(lx.matches('http://blah1.com/blah2'), False)
        self.assertEqual(lx.matches('http://blah2.com/blah1'), False)
        self.assertEqual(lx.matches('http://blah2.com/blah2'), False)

    def test_restrict_xpaths(self):
        lx = RegexLinkExtractor(restrict_xpaths=('//div[@id="subwrapper"]', ))
        self.assertEqual([link for link in lx.extract_links(self.response)],
            [ Link(url='http://example.com/sample1.html', text=u''),
              Link(url='http://example.com/sample2.html', text=u'sample 2') ])

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

        lx = RegexLinkExtractor(restrict_xpaths="//div[@class='links']") 
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://example.org/about.html', text=u'About us\xa3')])


class HTMLImageLinkExtractorTestCase(unittest.TestCase):
    def setUp(self):
        base_path = os.path.join(os.path.dirname(__file__), 'sample_data', 'link_extractor')
        body = open(os.path.join(base_path, 'image_linkextractor.html'), 'r').read()
        self.response = HtmlResponse(url='http://example.com/index', body=body)

    def tearDown(self):
        del self.response

    def test_urls_type(self):
        '''Test that the resulting urls are regular strings and not a unicode objects'''
        lx = HTMLImageLinkExtractor()
        links = lx.extract_links(self.response)
        self.assertTrue(all(isinstance(link.url, str) for link in links))

    def test_extraction(self):
        '''Test the extractor's behaviour among different situations'''

        lx = HTMLImageLinkExtractor(locations=('//img', ))
        links_1 = lx.extract_links(self.response)
        self.assertEqual(links_1,
            [ Link(url='http://example.com/sample1.jpg', text=u'sample 1'),
              Link(url='http://example.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://example.com/sample4.jpg', text=u'sample 4') ])

        lx = HTMLImageLinkExtractor(locations=('//img', ), unique=False)
        links_2 = lx.extract_links(self.response)
        self.assertEqual(links_2,
            [ Link(url='http://example.com/sample1.jpg', text=u'sample 1'),
              Link(url='http://example.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://example.com/sample4.jpg', text=u'sample 4'),
              Link(url='http://example.com/sample4.jpg', text=u'sample 4 repetition') ])

        lx = HTMLImageLinkExtractor(locations=('//div[@id="wrapper"]', ))
        links_3 = lx.extract_links(self.response)
        self.assertEqual(links_3,
            [ Link(url='http://example.com/sample1.jpg', text=u'sample 1'),
              Link(url='http://example.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://example.com/sample4.jpg', text=u'sample 4') ])

        lx = HTMLImageLinkExtractor(locations=('//a', ))
        links_4 = lx.extract_links(self.response)
        self.assertEqual(links_4,
            [ Link(url='http://example.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://example.com/sample3.html', text=u'sample 3') ])

if __name__ == "__main__":
    unittest.main()
