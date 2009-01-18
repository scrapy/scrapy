import unittest

from BeautifulSoup import BeautifulSoup

from scrapy.http import Response
from scrapy.contrib.response.soup import ResponseSoup

class ResponseSoupTest(unittest.TestCase):

    def setUp(self):
        ResponseSoup()

    def test_response_soup(self):
        r1 = Response('http://www.example.com', body='')

        soup1 = r1.getsoup()
        soup2 = r1.getsoup()

        assert isinstance(r1.soup, BeautifulSoup)
        assert isinstance(soup2, BeautifulSoup)
        # make sure it's cached
        assert soup1 is soup2

        # when body is None, an empty soup should be returned
        r1 = Response('http://www.example.com')
        assert r1.body is None
        assert isinstance(r1.getsoup(), BeautifulSoup)

    def test_response_soup_caching(self):
        r1 = Response('http://www.example.com', body='')
        soup1 = r1.getsoup()
        r2 = r1.copy()
        soup2 = r1.getsoup()
        soup3 = r2.getsoup()

        assert soup1 is soup2
        assert soup1 is not soup3
