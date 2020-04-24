from urllib.parse import urlparse
import unittest


class UrlparseTestCase(unittest.TestCase):

    def test_s3_url(self):
        p = urlparse('s3://bucket/key/name?param=value')
        self.assertEqual(p.scheme, 's3')
        self.assertEqual(p.hostname, 'bucket')
        self.assertEqual(p.path, '/key/name')
        self.assertEqual(p.query, 'param=value')
