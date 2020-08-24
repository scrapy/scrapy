import unittest

from scrapy.utils.http import decode_chunked_transfer


class ChunkedTest(unittest.TestCase):

    def test_decode_chunked_transfer(self):
        """Example taken from: http://en.wikipedia.org/wiki/Chunked_transfer_encoding"""
        chunked_body = "25\r\n" + "This is the data in the first chunk\r\n\r\n"
        chunked_body += "1C\r\n" + "and this is the second one\r\n\r\n"
        chunked_body += "3\r\n" + "con\r\n"
        chunked_body += "8\r\n" + "sequence\r\n"
        chunked_body += "0\r\n\r\n"
        body = decode_chunked_transfer(chunked_body)
        self.assertEqual(
            body,
            "This is the data in the first chunk\r\nand this is the second one\r\nconsequence"
        )
