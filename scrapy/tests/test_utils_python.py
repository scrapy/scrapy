import unittest

from scrapy.utils.python import str_to_unicode, unicode_to_str, \
    memoizemethod_noargs, isbinarytext

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

    def test_memoizemethod_noargs(self):
        class A(object):
            def __init__(self):
                self.cache = {}

            @memoizemethod_noargs
            def cached(self):
                return object()

            def noncached(self):
                return object()

        a = A()
        one = a.cached()
        two = a.cached()
        three = a.noncached()
        assert one is two
        assert one is not three

    def test_isbinarytext(self):

        # basic tests
        assert not isbinarytext("hello")

        # utf-16 strings contain null bytes
        assert not isbinarytext(u"hello".encode('utf-16')) 

        # one with encoding
        assert not isbinarytext("<div>Price \xa3</div>")

        # finally some real binary bytes
        assert isbinarytext("\x02\xa3")

if __name__ == "__main__":
    unittest.main()
