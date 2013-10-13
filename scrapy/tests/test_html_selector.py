import unittest

from scrapy.http import HtmlResponse
from scrapy.contrib.selector.html import HtmlXPathSelector


class HtmlXPathSelectorTest(unittest.TestCase):

    def test_extract_links(self):
        text = '<a href="somelink">Some Text</a>'
        hxs = HtmlXPathSelector(text=text)
        self.assertEqual(['somelink'], hxs.extract_links())
        self.assertEqual(['somelink'], hxs.extract_links(absolute=True))
        response = HtmlResponse('http://scrapinghub.com/services.html',
                body=text)
        hxs = HtmlXPathSelector(response=response)
        self.assertEqual(['somelink'], hxs.extract_links())
        self.assertEqual(['http://scrapinghub.com/somelink'],
                hxs.extract_links(absolute=True))
