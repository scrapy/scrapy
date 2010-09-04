from urlparse import urlparse
import unittest


class UrlparseTestCase(unittest.TestCase):

    def test_s3_netloc(self):
        self.assertEqual(urlparse('s3://bucket/key').netloc, 'bucket')
