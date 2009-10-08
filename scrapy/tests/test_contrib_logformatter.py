import unittest

from scrapy.http import Request, Response
from scrapy.contrib.logformatter import crawled_logline


class LoggingContribTest(unittest.TestCase):

    def test_crawled_logline(self):
        req = Request("http://www.example.com")
        res = Response("http://www.example.com")
        self.assertEqual(crawled_logline(req, res),
            "Crawled (200) <GET http://www.example.com> (referer: None)")

        req = Request("http://www.example.com", headers={'referer': 'http://example.com'})
        res = Response("http://www.example.com", flags=['cached'])
        self.assertEqual(crawled_logline(req, res),
            "Crawled (200) <GET http://www.example.com> (referer: http://example.com) ['cached']")


if __name__ == "__main__":
    unittest.main()
