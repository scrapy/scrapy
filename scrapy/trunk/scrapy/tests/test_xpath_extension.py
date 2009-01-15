import unittest

from scrapy.http import Response
from scrapy.xpath.extension import ResponseLibxml2

class ResponseLibxml2Test(unittest.TestCase):

    def setUp(self):
        ResponseLibxml2()

    def test_response_libxml2_caching(self):
        r1 = Response('example.com', 'http://www.example.com', body='<html><head></head><body></body></html>')
        r2 = r1.copy()

        doc1 = r1.getlibxml2doc()
        doc2 = r1.getlibxml2doc()
        doc3 = r2.getlibxml2doc()

        # make sure it's cached
        assert doc1 is doc2
        assert doc1 is not doc3

        # don't leave libxml2 documents in memory to avoid wrong libxml2 leaks reports
        del doc1, doc2, doc3

