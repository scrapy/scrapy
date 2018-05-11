import unittest
from six.moves.urllib.parse import urlparse

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

        assert req1a == req2
        assert req1a == urlp
        assert req1a is req1b
        assert req1a is not req2
        assert req1a is not req2

    def test_urlparse_cached_strip(self):

        #Test out that urlparse_cached strips out any \n
        # or \t from its url

        normal_url = "http://quotes.toscrape.com/"
        dirty_url = "\nhttp://quotes.toscrape.com/\n"

        request1 = Request(normal_url)
        request2 = Request(dirty_url)
        req1 = urlparse_cached(request1)
        req2 = urlparse_cached(request2)
        urlp = urlparse(url)

        assert req1 == req2
        assert req1 != urlp




if __name__ == "__main__":
    unittest.main()
