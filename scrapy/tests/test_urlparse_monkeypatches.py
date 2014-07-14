from six.moves.urllib.parse import urlparse
import unittest


class UrlparseTestCase(unittest.TestCase):

    def test_s3_url(self):
        p = urlparse('s3://bucket/key/name?param=value')
        self.assertEquals(p.scheme, 's3')
        self.assertEquals(p.hostname, 'bucket')
        self.assertEquals(p.path, '/key/name')
        self.assertEquals(p.query, 'param=value')
