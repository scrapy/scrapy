import unittest
from os.path import join

from w3lib.encoding import html_to_unicode

from scrapy.utils.gz import gunzip, gzip_magic_number
from scrapy.http import Response
from tests import tests_datadir


SAMPLEDIR = join(tests_datadir, 'compressed')


class GunzipTest(unittest.TestCase):

    def test_gunzip_basic(self):
        with open(join(SAMPLEDIR, 'feed-sample1.xml.gz'), 'rb') as f:
            r1 = Response("http://www.example.com", body=f.read())
            self.assertTrue(gzip_magic_number(r1))

            r2 = Response("http://www.example.com", body=gunzip(r1.body))
            self.assertFalse(gzip_magic_number(r2))
            self.assertEqual(len(r2.body), 9950)

    def test_gunzip_truncated(self):
        with open(join(SAMPLEDIR, 'truncated-crc-error.gz'), 'rb') as f:
            text = gunzip(f.read())
            assert text.endswith(b'</html')

    def test_gunzip_no_gzip_file_raises(self):
        with open(join(SAMPLEDIR, 'feed-sample1.xml'), 'rb') as f:
            self.assertRaises(IOError, gunzip, f.read())

    def test_gunzip_truncated_short(self):
        with open(join(SAMPLEDIR, 'truncated-crc-error-short.gz'), 'rb') as f:
            r1 = Response("http://www.example.com", body=f.read())
            self.assertTrue(gzip_magic_number(r1))

            r2 = Response("http://www.example.com", body=gunzip(r1.body))
            assert r2.body.endswith(b'</html>')
            self.assertFalse(gzip_magic_number(r2))

    def test_is_gzipped_empty(self):
        r1 = Response("http://www.example.com")
        self.assertFalse(gzip_magic_number(r1))

    def test_gunzip_illegal_eof(self):
        with open(join(SAMPLEDIR, 'unexpected-eof.gz'), 'rb') as f:
            text = html_to_unicode('charset=cp1252', gunzip(f.read()))[1]
            with open(join(SAMPLEDIR, 'unexpected-eof-output.txt'), 'rb') as o:
                expected_text = o.read().decode("utf-8")
                self.assertEqual(len(text), len(expected_text))
                self.assertEqual(text, expected_text)
