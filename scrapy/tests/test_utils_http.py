import unittest
from scrapy.utils.http import basic_auth_header

__doctests__ = ['scrapy.utils.http']

class UtilsHttpTestCase(unittest.TestCase):

    def test_basic_auth_header(self):
        self.assertEqual('Basic c29tZXVzZXI6c29tZXBhc3M=',
                basic_auth_header('someuser', 'somepass'))
        # Check url unsafe encoded header
        self.assertEqual('Basic c29tZXVzZXI6QDx5dTk-Jm8_UQ==',
            basic_auth_header('someuser', '@<yu9>&o?Q'))
