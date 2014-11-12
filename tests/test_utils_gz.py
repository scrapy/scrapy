import unittest
from os.path import join

from scrapy.utils.gz import gunzip
from tests import tests_datadir

SAMPLEDIR = join(tests_datadir, 'compressed')


class GzTest(unittest.TestCase):

    def test_gunzip_basic(self):
        with open(join(SAMPLEDIR, 'feed-sample1.xml.gz'), 'rb') as f:
            text = gunzip(f.read())
            self.assertEqual(len(text), 9950)

    def test_gunzip_truncated(self):
        with open(join(SAMPLEDIR, 'truncated-crc-error.gz'), 'rb') as f:
            text = gunzip(f.read())
            assert text.endswith(b'</html')

    def test_gunzip_no_gzip_file_raises(self):
        with open(join(SAMPLEDIR, 'feed-sample1.xml'), 'rb') as f:
            self.assertRaises(IOError, gunzip, f.read())

    def test_gunzip_truncated_short(self):
        with open(join(SAMPLEDIR, 'truncated-crc-error-short.gz'), 'rb') as f:
            text = gunzip(f.read())
            assert text.endswith(b'</html>')
