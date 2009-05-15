from unittest import TestCase, main
from scrapy.http import Response, XmlResponse
from scrapy.contrib_exp.downloadermiddleware.decompression import DecompressionMiddleware
from scrapy.tests import get_testdata

def setUp():
    formats = ['tar', 'xml.bz2', 'xml.gz', 'zip']
    uncompressed_body = get_testdata('compressed', 'feed-sample1.xml')
    test_responses = {}
    for format in formats:
        body = get_testdata('compressed', 'feed-sample1.' + format)
        test_responses[format] = Response('http://foo.com/bar', body=body)
    return uncompressed_body, test_responses

class ScrapyDecompressionTest(TestCase):
    uncompressed_body, test_responses = setUp()
    middleware = DecompressionMiddleware()

    def test_tar(self):
        response, format = self.middleware.extract(self.test_responses['tar'])
        assert isinstance(response, XmlResponse)
        self.assertEqual(response.body, self.uncompressed_body)

    def test_zip(self):
        response, format = self.middleware.extract(self.test_responses['zip'])
        assert isinstance(response, XmlResponse)
        self.assertEqual(response.body, self.uncompressed_body)

    def test_gz(self):
        response, format = self.middleware.extract(self.test_responses['xml.gz'])
        assert isinstance(response, XmlResponse)
        self.assertEqual(response.body, self.uncompressed_body)

    def test_bz2(self):
        response, format = self.middleware.extract(self.test_responses['xml.bz2'])
        assert isinstance(response, XmlResponse)
        self.assertEqual(response.body, self.uncompressed_body)

if __name__ == '__main__':
    main()
