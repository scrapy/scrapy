import unittest
import six

from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.item import Item, Field
from scrapy.logformatter import LogFormatter


class CustomItem(Item):

    name = Field()

    def __str__(self):
        return "name: %s" % self['name']


class LoggingContribTest(unittest.TestCase):

    def setUp(self):
        self.formatter = LogFormatter()
        self.spider = Spider('default')

    def test_crawled(self):
        req = Request("http://www.example.com")
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(logline,
            "Crawled (200) <GET http://www.example.com> (referer: None)")

        req = Request("http://www.example.com", headers={'referer': 'http://example.com'})
        res = Response("http://www.example.com", flags=['cached'])
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(logline,
            "Crawled (200) <GET http://www.example.com> (referer: http://example.com) ['cached']")

    def test_flags_in_request(self):
        req = Request("http://www.example.com", flags=['test','flag'])
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(logline,
        "Crawled (200) <GET http://www.example.com> ['test', 'flag'] (referer: None)")

    def test_dropped(self):
        item = {}
        exception = Exception(u"\u2018")
        response = Response("http://www.example.com")
        logkws = self.formatter.dropped(item, exception, response, self.spider)
        logline = logkws['msg'] % logkws['args']
        lines = logline.splitlines()
        assert all(isinstance(x, six.text_type) for x in lines)
        self.assertEqual(lines, [u"Dropped: \u2018", '{}'])

    def test_scraped(self):
        item = CustomItem()
        item['name'] = u'\xa3'
        response = Response("http://www.example.com")
        logkws = self.formatter.scraped(item, response, self.spider)
        logline = logkws['msg'] % logkws['args']
        lines = logline.splitlines()
        assert all(isinstance(x, six.text_type) for x in lines)
        self.assertEqual(lines, [u"Scraped from <200 http://www.example.com>", u'name: \xa3'])

if __name__ == "__main__":
    unittest.main()
