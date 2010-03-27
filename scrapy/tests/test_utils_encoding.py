import unittest

from scrapy.utils.encoding import encoding_exists, resolve_encoding

class UtilsEncodingTestCase(unittest.TestCase):

    _ENCODING_ALIASES = {
        'foo': 'cp1252',
        'bar': 'none',
    }

    def test_resolve_encoding(self):
        self.assertEqual(resolve_encoding('latin1', self._ENCODING_ALIASES),
                         'latin1')
        self.assertEqual(resolve_encoding('foo', self._ENCODING_ALIASES),
                         'cp1252')

    def test_encoding_exists(self):
        assert encoding_exists('latin1', self._ENCODING_ALIASES)
        assert encoding_exists('foo', self._ENCODING_ALIASES)
        assert not encoding_exists('bar', self._ENCODING_ALIASES)
        assert not encoding_exists('none', self._ENCODING_ALIASES)

if __name__ == "__main__":
    unittest.main()
