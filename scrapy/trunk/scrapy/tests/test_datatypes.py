import unittest

from scrapy.utils.datatypes import CaselessDict


class CaselessDictTest(unittest.TestCase):

    def test_init(self):
        seq = {'red': 1, 'black': 3}
        d = CaselessDict(seq)
        self.assertEqual(d['red'], 1)
        self.assertEqual(d['black'], 3)

        seq = (('red', 1), ('black', 3))
        d = CaselessDict(seq)
        self.assertEqual(d['red'], 1)
        self.assertEqual(d['black'], 3)

    def test_caseless(self):
        d = CaselessDict()
        d['key_Lower'] = 1
        self.assertEqual(d['KEy_loWer'], 1)
        self.assertEqual(d.get('KEy_loWer'), 1)

        d['KEY_LOWER'] = 3
        self.assertEqual(d['key_Lower'], 3)
        self.assertEqual(d.get('key_Lower'), 3)

    def test_delete(self):
        d = CaselessDict({'key_lower': 1})
        del d['key_LOWER']
        self.assertRaises(KeyError, d.__getitem__, 'key_LOWER')
        self.assertRaises(KeyError, d.__getitem__, 'key_lower')

    def test_getdefault(self):
        d = CaselessDict()
        self.assertEqual(d.get('c', 5), 5)
        d['c'] = 10
        self.assertEqual(d.get('c', 5), 10)

    def test_setdefault(self):
        d = CaselessDict({'a': 1, 'b': 2})

        r = d.setdefault('A', 5)
        self.assertEqual(r, 1)
        self.assertEqual(d['A'], 1)

        r = d.setdefault('c', 5)
        self.assertEqual(r, 5)
        self.assertEqual(d['C'], 5)

    def test_fromkeys(self):
        keys = ('a', 'b')

        d = CaselessDict.fromkeys(keys)
        self.assertEqual(d['A'], None)
        self.assertEqual(d['B'], None)

        d = CaselessDict.fromkeys(keys, 1)
        self.assertEqual(d['A'], 1)
        self.assertEqual(d['B'], 1)

        instance = CaselessDict()
        d = instance.fromkeys(keys)
        self.assertEqual(d['A'], None)
        self.assertEqual(d['B'], None)

        d = instance.fromkeys(keys, 1)
        self.assertEqual(d['A'], 1)
        self.assertEqual(d['B'], 1)

    def test_contains(self):
        d = CaselessDict()
        d['a'] = 1
        assert 'a' in d
        assert d.has_key('a')

    def test_pop(self):
        d = CaselessDict()
        d['a'] = 1
        self.assertEqual(d.pop('A'), 1)
        self.assertRaises(KeyError, d.pop, 'A')

