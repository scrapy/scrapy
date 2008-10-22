import unittest

from scrapy.http import Response
from scrapy.link import LinkExtractor

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
                         {'http://example.org/somepage/item/12.html': 'Item 12', 
                          'http://example.org/about.html': 'About us', 
                          'http://example.org/othercat.html': 'Other category', 
                          'http://example.org/': ''})

    def test_base_url(self):
        html = """<html><head><title>Page title<title><base href="http://otherdomain.com/base/" />
        <body><p><a href="item/12.html">Item 12</a></p>
        </body></html>"""
        response = Response("example.org", "http://example.org/somepage/index.html", body=html)

        lx = LinkExtractor()  # default: tag=a, attr=href
        self.assertEqual(lx.extract_urls(response), 
                         {'http://otherdomain.com/base/item/12.html': 'Item 12'})

if __name__ == "__main__":
    unittest.main()
