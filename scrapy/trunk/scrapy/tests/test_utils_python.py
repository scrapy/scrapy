import unittest

from scrapy.utils.python import str_to_unicode, unicode_to_str

class UtilsPythonTestCase(unittest.TestCase):
    def test_str_to_unicode(self):
        # converting an utf-8 encoded string to unicode
        self.assertEqual(str_to_unicode('lel\xc3\xb1e'), u'lel\xf1e')

        # converting a latin-1 encoded string to unicode
        self.assertEqual(str_to_unicode('lel\xf1e', 'latin-1'), u'lel\xf1e')

        # converting a unicode to unicode should return the same object
        self.assertEqual(str_to_unicode(u'\xf1e\xf1e\xf1e'), u'\xf1e\xf1e\xf1e')

        # converting a strange object should raise TypeError
        self.assertRaises(TypeError, str_to_unicode, 423)

    def test_unicode_to_str(self):
        # converting a unicode object to an utf-8 encoded string
        self.assertEqual(unicode_to_str(u'\xa3 49'), '\xc2\xa3 49')

        # converting a unicode object to a latin-1 encoded string
        self.assertEqual(unicode_to_str(u'\xa3 49', 'latin-1'), '\xa3 49')

        # converting a regular string to string should return the same object
        self.assertEqual(unicode_to_str('lel\xf1e'), 'lel\xf1e')

        # converting a strange object should raise TypeError
        self.assertRaises(TypeError, unicode_to_str, unittest)

if __name__ == "__main__":
    unittest.main()
