import unittest

from scrapy.spider import BaseSpider
from scrapy.http import Request, Response
from scrapy.logformatter import LogFormatter


class LoggingContribTest(unittest.TestCase):

    def setUp(self):
        self.formatter = LogFormatter()
        self.spider = BaseSpider('default')

    def test_crawled(self):
        req = Request("http://www.example.com")
        res = Response("http://www.example.com")
        self.assertEqual(self.formatter.crawled(req, res, self.spider),
            "Crawled (200) <GET http://www.example.com> (referer: None)")

        req = Request("http://www.example.com", headers={'referer': 'http://example.com'})
        res = Response("http://www.example.com", flags=['cached'])
        self.assertEqual(self.formatter.crawled(req, res, self.spider),
            "Crawled (200) <GET http://www.example.com> (referer: http://example.com) ['cached']")

    def test_dropped(self):
        item = {}
        exception = Exception(u"\u2018")
        response = Response("http://www.example.com")
        lines = self.formatter.dropped(item, exception, response, self.spider).splitlines()
        self.assertEqual(lines, [u"Dropped: \u2018", '{}'])

if __name__ == "__main__":
    unittest.main()
