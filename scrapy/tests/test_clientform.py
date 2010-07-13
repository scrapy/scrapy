import unittest

from scrapy.xlib import ClientForm

class ClientFormPatchTests(unittest.TestCase):

    def test_patched_unescape_charref(self):
        self.assertEqual(ClientForm.unescape_charref('c', 'utf-8'), 'c')
