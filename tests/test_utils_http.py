import unittest

from scrapy.utils.http import decode_chunked_transfer

class ChunkedTest(unittest.TestCase):

    def test_decode_chunked_transfer(self):
        """Example taken from: http://en.wikipedia.org/wiki/Chunked_transfer_encoding"""
        chunked_body = b"25\r\n" + b"This is the data in the first chunk\r\n\r\n"
        chunked_body += b"1C\r\n" + b"and this is the second one\r\n\r\n"
        chunked_body += b"3\r\n" + b"con\r\n"
        chunked_body += b"8\r\n" + b"sequence\r\n"
        chunked_body += b"0\r\n\r\n"
        body = decode_chunked_transfer(chunked_body)
        self.assertEqual(body,
            b"This is the data in the first chunk\r\n"
            b"and this is the second one\r\n"
            b"consequence")


