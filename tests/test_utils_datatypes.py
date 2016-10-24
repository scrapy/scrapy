import copy
import time
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from scrapy.utils.datatypes import CaselessDict, ExpiringCache

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


class ExpiringCacheTest(unittest.TestCase):
    def test_expiration(self):
        cache = ExpiringCache(limit=1000, expiration=100)

        now = time.time()
        later = now + 50
        after_expiration = now + 110

        with mock.patch('time.time', return_value=now):
            cache['key'] = "some value"

        with mock.patch('time.time', return_value=later):
            assert cache['key'] == "some value"

        with mock.patch('time.time', return_value=after_expiration):
            with self.assertRaises(KeyError):
                cache['key']

    def test_limit(self):
        cache = ExpiringCache(limit=1000, expiration=None)

        for i in range(1001):
            cache[i] = str(i)

        with self.assertRaises(KeyError):
            cache[0]

        assert cache[1] == "1"
        assert list(cache.keys()) == list(range(1, 1001))

    def test_dict_methods(self):
        cache = ExpiringCache(limit=1000, expiration=100)

        cache["a"] = 1
        assert cache.get("a") == 1
        assert cache.get("b") == None
        assert cache.setdefault("c", 3) == 3
        assert cache["c"] == 3
        assert list(cache.items()) == [("a", 1), ("c", 3)]
        assert list(cache.values()) == [1, 3]


if __name__ == "__main__":
    unittest.main()
