import unittest

from scrapy.http import Response
from scrapy.link import LinkExtractor, Link
from scrapy.link.extractors import RegexLinkExtractor

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
        self.assertEqual(lx.extract_urls(response), 
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
        self.assertEqual(lx.extract_urls(response), 
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

if __name__ == "__main__":
    unittest.main()
