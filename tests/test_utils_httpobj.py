import unittest
from urllib.parse import urlparse

from scrapy.http import Request
from scrapy.utils.httpobj import urlparse_cached


class HttpobjUtilsTest(unittest.TestCase):

    def test_urlparse_cached(self):
        url = "http://www.example.com/index.html"
        request1 = Request(url)
        request2 = Request(url)
        req1a = urlparse_cached(request1)
        req1b = urlparse_cached(request1)
        req2 = urlparse_cached(request2)
        urlp = urlparse(url)

        self.assertEqual(req1a , req2)
        self.assertEqual(req1a , urlp)
        self.assertIs(req1a, req1b)
        self.assertIsNot(req1a, req2)
        self.assertIsNot(req1a, req2)


if __name__ == "__main__":
    unittest.main()
