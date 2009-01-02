import os
import unittest

from scrapy.http.response import Response, ResponseBody
from scrapy.link import LinkExtractor, Link
from scrapy.link.extractors import RegexLinkExtractor, ImageLinkExtractor

class LinkExtractorTestCase(unittest.TestCase):
    def test_basic(self):
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/" /></p>
        </body></html>"""
        response = Response("example.org", "http://example.org/somepage/index.html", body=html)

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
        response = Response("example.org", "http://example.org/somepage/index.html", body=html)

        lx = LinkExtractor()  # default: tag=a, attr=href
        self.assertEqual(lx.extract_links(response),
                         [Link(url='http://otherdomain.com/base/item/12.html', text='Item 12')])

    def test_matches(self):
        url1 = 'http://lotsofstuff.com/stuff1/index'
        url2 = 'http://evenmorestuff.com/uglystuff/index'

        lx = LinkExtractor()
        self.assertEqual(lx.matches(url1), True)
        self.assertEqual(lx.matches(url2), True)

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

class ImageLinkExtractorTestCase(unittest.TestCase):
    def setUp(self):
        body = open(os.path.join(os.path.dirname(__file__), 'sample_data/image_linkextractor.html'), 'r').read()
        self.response = Response(url='http://examplesite.com/index', domain='examplesite.com', body=ResponseBody(body))

    def test_urls_type(self):
        '''Test that the resulting urls are regular strings and not a unicode objects'''
        lx = ImageLinkExtractor()
        links = lx.extract_links(self.response)
        self.assertTrue(all(isinstance(link.url, str) for link in links))

    def test_extraction(self):
        '''Test the extractor's behaviour among different situations'''
        lx = ImageLinkExtractor()

        links_1 = lx.extract_links(self.response) # using default locations (//img)
        self.assertEqual(links_1,
            [ Link(url='http://examplesite.com/sample1.jpg', text=u'sample 1'),
              Link(url='http://examplesite.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://examplesite.com/sample4.jpg', text=u'sample 4') ])

        links_2 = lx.extract_links(self.response, unique=False) # using default locations and unique=False
        self.assertEqual(links_2,
            [ Link(url='http://examplesite.com/sample1.jpg', text=u'sample 1'),
              Link(url='http://examplesite.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://examplesite.com/sample4.jpg', text=u'sample 4'),
              Link(url='http://examplesite.com/sample4.jpg', text=u'sample 4 repetition') ])

        links_3 = lx.extract_links(self.response, locations=('//div[@id="wrapper"]', ))
        self.assertEqual(links_3,
            [ Link(url='http://examplesite.com/sample1.jpg', text=u'sample 1'),
              Link(url='http://examplesite.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://examplesite.com/sample4.jpg', text=u'sample 4') ])

        links_4 = lx.extract_links(self.response, locations=('//a', ))
        self.assertEqual(links_4,
            [ Link(url='http://examplesite.com/sample2.jpg', text=u'sample 2'),
              Link(url='http://examplesite.com/sample3.html', text=u'sample 3') ])

if __name__ == "__main__":
    unittest.main()
