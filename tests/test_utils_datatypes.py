import copy
import unittest
import warnings
from collections.abc import Iterator, Mapping, MutableMapping

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.utils.datatypes import (
    CaseInsensitiveDict,
    CaselessDict,
    LocalCache,
    LocalWeakReferencedCache,
    SequenceExclude,
)
from scrapy.utils.python import garbage_collect

__doctests__ = ["scrapy.utils.datatypes"]


class CaseInsensitiveDictMixin:
    def test_init_dict(self):
        seq = {"red": 1, "black": 3}
        d = self.dict_class(seq)
        self.assertEqual(d["red"], 1)
        self.assertEqual(d["black"], 3)

    def test_init_pair_sequence(self):
        seq = (("red", 1), ("black", 3))
        d = self.dict_class(seq)
        self.assertEqual(d["red"], 1)
        self.assertEqual(d["black"], 3)

    def test_init_mapping(self):
        class MyMapping(Mapping):
            def __init__(self, **kwargs):
                self._d = kwargs

            def __getitem__(self, key):
                return self._d[key]

            def __iter__(self):
                return iter(self._d)

            def __len__(self):
                return len(self._d)

        seq = MyMapping(red=1, black=3)
        d = self.dict_class(seq)
        self.assertEqual(d["red"], 1)
        self.assertEqual(d["black"], 3)

    def test_init_mutable_mapping(self):
        class MyMutableMapping(MutableMapping):
            def __init__(self, **kwargs):
                self._d = kwargs

            def __getitem__(self, key):
                return self._d[key]

            def __setitem__(self, key, value):
                self._d[key] = value

            def __delitem__(self, key):
                del self._d[key]

            def __iter__(self):
                return iter(self._d)

            def __len__(self):
                return len(self._d)

        seq = MyMutableMapping(red=1, black=3)
        d = self.dict_class(seq)
        self.assertEqual(d["red"], 1)
        self.assertEqual(d["black"], 3)

    def test_caseless(self):
        d = self.dict_class()
        d["key_Lower"] = 1
        self.assertEqual(d["KEy_loWer"], 1)
        self.assertEqual(d.get("KEy_loWer"), 1)

        d["KEY_LOWER"] = 3
        self.assertEqual(d["key_Lower"], 3)
        self.assertEqual(d.get("key_Lower"), 3)

    def test_delete(self):
        d = self.dict_class({"key_lower": 1})
        del d["key_LOWER"]
        self.assertRaises(KeyError, d.__getitem__, "key_LOWER")
        self.assertRaises(KeyError, d.__getitem__, "key_lower")

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_getdefault(self):
        d = CaselessDict()
        self.assertEqual(d.get("c", 5), 5)
        d["c"] = 10
        self.assertEqual(d.get("c", 5), 10)

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_setdefault(self):
        d = CaselessDict({"a": 1, "b": 2})

        r = d.setdefault("A", 5)
        self.assertEqual(r, 1)
        self.assertEqual(d["A"], 1)

        r = d.setdefault("c", 5)
        self.assertEqual(r, 5)
        self.assertEqual(d["C"], 5)

    def test_fromkeys(self):
        keys = ("a", "b")

        d = self.dict_class.fromkeys(keys)
        self.assertEqual(d["A"], None)
        self.assertEqual(d["B"], None)

        d = self.dict_class.fromkeys(keys, 1)
        self.assertEqual(d["A"], 1)
        self.assertEqual(d["B"], 1)

        instance = self.dict_class()
        d = instance.fromkeys(keys)
        self.assertEqual(d["A"], None)
        self.assertEqual(d["B"], None)

        d = instance.fromkeys(keys, 1)
        self.assertEqual(d["A"], 1)
        self.assertEqual(d["B"], 1)

    def test_contains(self):
        d = self.dict_class()
        d["a"] = 1
        assert "A" in d

    def test_pop(self):
        d = self.dict_class()
        d["a"] = 1
        self.assertEqual(d.pop("A"), 1)
        self.assertRaises(KeyError, d.pop, "A")

    def test_normkey(self):
        class MyDict(self.dict_class):
            def _normkey(self, key):
                return key.title()

            normkey = _normkey  # deprecated CaselessDict class

        d = MyDict()
        d["key-one"] = 2
        self.assertEqual(list(d.keys()), ["Key-One"])

    def test_normvalue(self):
        class MyDict(self.dict_class):
            def _normvalue(self, value):
                if value is not None:
                    return value + 1
                return None

            normvalue = _normvalue  # deprecated CaselessDict class

        d = MyDict({"key": 1})
        self.assertEqual(d["key"], 2)
        self.assertEqual(d.get("key"), 2)

        d = MyDict()
        d["key"] = 1
        self.assertEqual(d["key"], 2)
        self.assertEqual(d.get("key"), 2)

        d = MyDict()
        d.setdefault("key", 1)
        self.assertEqual(d["key"], 2)
        self.assertEqual(d.get("key"), 2)

        d = MyDict()
        d.update({"key": 1})
        self.assertEqual(d["key"], 2)
        self.assertEqual(d.get("key"), 2)

        d = MyDict.fromkeys(("key",), 1)
        self.assertEqual(d["key"], 2)
        self.assertEqual(d.get("key"), 2)

    def test_copy(self):
        h1 = self.dict_class({"header1": "value"})
        h2 = copy.copy(h1)
        assert isinstance(h2, self.dict_class)
        self.assertEqual(h1, h2)
        self.assertEqual(h1.get("header1"), h2.get("header1"))
        self.assertEqual(h1.get("header1"), h2.get("HEADER1"))
        h3 = h1.copy()
        assert isinstance(h3, self.dict_class)
        self.assertEqual(h1, h3)
        self.assertEqual(h1.get("header1"), h3.get("header1"))
        self.assertEqual(h1.get("header1"), h3.get("HEADER1"))


class CaseInsensitiveDictTest(CaseInsensitiveDictMixin, unittest.TestCase):
    dict_class = CaseInsensitiveDict

    def test_repr(self):
        d1 = self.dict_class({"foo": "bar"})
        self.assertEqual(repr(d1), "<CaseInsensitiveDict: {'foo': 'bar'}>")
        d2 = self.dict_class({"AsDf": "QwErTy", "FoO": "bAr"})
        self.assertEqual(
            repr(d2), "<CaseInsensitiveDict: {'AsDf': 'QwErTy', 'FoO': 'bAr'}>"
        )

    def test_iter(self):
        d = self.dict_class({"AsDf": "QwErTy", "FoO": "bAr"})
        iterkeys = iter(d)
        self.assertIsInstance(iterkeys, Iterator)
        self.assertEqual(list(iterkeys), ["AsDf", "FoO"])


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class CaselessDictTest(CaseInsensitiveDictMixin, unittest.TestCase):
    dict_class = CaselessDict

    def test_deprecation_message(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.filterwarnings("always", category=ScrapyDeprecationWarning)
            self.dict_class({"foo": "bar"})

            self.assertEqual(len(caught), 1)
            self.assertTrue(issubclass(caught[0].category, ScrapyDeprecationWarning))
            self.assertEqual(
                "scrapy.utils.datatypes.CaselessDict is deprecated,"
                " please use scrapy.utils.datatypes.CaseInsensitiveDict instead",
                str(caught[0].message),
            )


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

    def test_range_step(self):
        seq = range(10, 20, 3)
        d = SequenceExclude(seq)
        are_not_in = [v for v in range(10, 20, 3) if v in d]
        self.assertEqual([], are_not_in)

        are_not_in = [v for v in range(10, 20) if v in d]
        self.assertEqual([11, 12, 14, 15, 17, 18], are_not_in)

    def test_string_seq(self):
        seq = "cde"
        d = SequenceExclude(seq)
        chars = "".join(v for v in "abcdefg" if v in d)
        self.assertEqual("abfg", chars)

    def test_stringset_seq(self):
        seq = set("cde")
        d = SequenceExclude(seq)
        chars = "".join(v for v in "abcdefg" if v in d)
        self.assertEqual("abfg", chars)

    def test_set(self):
        """Anything that is not in the supplied sequence will evaluate as 'in' the container."""
        seq = {-3, "test", 1.1}
        d = SequenceExclude(seq)
        self.assertIn(0, d)
        self.assertIn("foo", d)
        self.assertIn(3.14, d)
        self.assertIn(set("bar"), d)

        # supplied sequence is a set, so checking for list (non)inclusion fails
        self.assertRaises(TypeError, (0, 1, 2) in d)
        self.assertRaises(TypeError, d.__contains__, ["a", "b", "c"])

        for v in [-3, "test", 1.1]:
            self.assertNotIn(v, d)


class LocalCacheTest(unittest.TestCase):
    def test_cache_with_limit(self):
        cache = LocalCache(limit=2)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        self.assertEqual(len(cache), 2)
        self.assertNotIn("a", cache)
        self.assertIn("b", cache)
        self.assertIn("c", cache)
        self.assertEqual(cache["b"], 2)
        self.assertEqual(cache["c"], 3)

    def test_cache_without_limit(self):
        maximum = 10**4
        cache = LocalCache()
        for x in range(maximum):
            cache[str(x)] = x
        self.assertEqual(len(cache), maximum)
        for x in range(maximum):
            self.assertIn(str(x), cache)
            self.assertEqual(cache[str(x)], x)


class LocalWeakReferencedCacheTest(unittest.TestCase):
    def test_cache_with_limit(self):
        cache = LocalWeakReferencedCache(limit=2)
        r1 = Request("https://example.org")
        r2 = Request("https://example.com")
        r3 = Request("https://example.net")
        cache[r1] = 1
        cache[r2] = 2
        cache[r3] = 3
        self.assertEqual(len(cache), 2)
        self.assertNotIn(r1, cache)
        self.assertIn(r2, cache)
        self.assertIn(r3, cache)
        self.assertEqual(cache[r1], None)
        self.assertEqual(cache[r2], 2)
        self.assertEqual(cache[r3], 3)
        del r2

        # PyPy takes longer to collect dead references
        garbage_collect()

        self.assertEqual(len(cache), 1)

    def test_cache_non_weak_referenceable_objects(self):
        cache = LocalWeakReferencedCache()
        k1 = None
        k2 = 1
        k3 = [1, 2, 3]
        cache[k1] = 1
        cache[k2] = 2
        cache[k3] = 3
        self.assertNotIn(k1, cache)
        self.assertNotIn(k2, cache)
        self.assertNotIn(k3, cache)
        self.assertEqual(len(cache), 0)

    def test_cache_without_limit(self):
        max = 10**4
        cache = LocalWeakReferencedCache()
        refs = []
        for x in range(max):
            refs.append(Request(f"https://example.org/{x}"))
            cache[refs[-1]] = x
        self.assertEqual(len(cache), max)
        for i, r in enumerate(refs):
            self.assertIn(r, cache)
            self.assertEqual(cache[r], i)
        del r  # delete reference to the last object in the list  # pylint: disable=undefined-loop-variable

        # delete half of the objects, make sure that is reflected in the cache
        for _ in range(max // 2):
            refs.pop()

        # PyPy takes longer to collect dead references
        garbage_collect()

        self.assertEqual(len(cache), max // 2)
        for i, r in enumerate(refs):
            self.assertIn(r, cache)
            self.assertEqual(cache[r], i)


if __name__ == "__main__":
    unittest.main()
