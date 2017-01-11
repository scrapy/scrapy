import copy
import unittest

from scrapy.utils.datatypes import CaselessDict, SequenceExclude

__doctests__ = ['scrapy.utils.datatypes']

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

    def test_pop(self):
        d = CaselessDict()
        d['a'] = 1
        self.assertEqual(d.pop('A'), 1)
        self.assertRaises(KeyError, d.pop, 'A')

    def test_normkey(self):
        class MyDict(CaselessDict):
            def normkey(self, key):
                return key.title()

        d = MyDict()
        d['key-one'] = 2
        self.assertEqual(list(d.keys()), ['Key-One'])

    def test_normvalue(self):
        class MyDict(CaselessDict):
            def normvalue(self, value):
                if value is not None:
                    return value + 1

        d = MyDict({'key': 1})
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict()
        d['key'] = 1
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict()
        d.setdefault('key', 1)
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict()
        d.update({'key': 1})
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict.fromkeys(('key',), 1)
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

    def test_copy(self):
        h1 = CaselessDict({'header1': 'value'})
        h2 = copy.copy(h1)
        self.assertEqual(h1, h2)
        self.assertEqual(h1.get('header1'), h2.get('header1'))
        assert isinstance(h2, CaselessDict)


class SequenceExcludeTest(unittest.TestCase):

    def test_list(self):
        seq = [1, 2, 3]
        d = SequenceExclude(seq)
        self.assertIn(0, d)
        self.assertIn(4, d)
        self.assertNotIn(2, d)

    def test_range(self):
        seq = range(10, 20)
        d = SequenceExclude(seq)
        self.assertIn(5, d)
        self.assertIn(20, d)
        self.assertNotIn(15, d)

    def test_six_range(self):
        import six.moves
        seq = six.moves.range(10**3, 10**6)
        d = SequenceExclude(seq)
        self.assertIn(10**2, d)
        self.assertIn(10**7, d)
        self.assertNotIn(10**4, d)

    def test_range_step(self):
        seq = range(10, 20, 3)
        d = SequenceExclude(seq)
        are_not_in = [v for v in range(10, 20, 3) if v in d]
        self.assertEquals([], are_not_in)

        are_not_in = [v for v in range(10, 20) if v in d]
        self.assertEquals([11, 12, 14, 15, 17, 18], are_not_in)

    def test_string_seq(self):
        seq = "cde"
        d = SequenceExclude(seq)
        chars = "".join(v for v in "abcdefg" if v in d)
        self.assertEquals("abfg", chars)

    def test_stringset_seq(self):
        seq = set("cde")
        d = SequenceExclude(seq)
        chars = "".join(v for v in "abcdefg" if v in d)
        self.assertEquals("abfg", chars)

    def test_set(self):
        """Anything that is not in the supplied sequence will evaluate as 'in' the container."""
        seq = set([-3, "test", 1.1])
        d = SequenceExclude(seq)
        self.assertIn(0, d)
        self.assertIn("foo", d)
        self.assertIn(3.14, d)
        self.assertIn(set("bar"), d)

        # supplied sequence is a set, so checking for list (non)inclusion fails
        self.assertRaises(TypeError, (0, 1, 2) in d)
        self.assertRaises(TypeError, d.__contains__, ['a', 'b', 'c'])

        for v in [-3, "test", 1.1]:
            self.assertNotIn(v, d)

if __name__ == "__main__":
    unittest.main()

