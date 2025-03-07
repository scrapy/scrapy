import copy
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


class CaseInsensitiveDictBase:
    def test_init_dict(self):
        seq = {"red": 1, "black": 3}
        d = self.dict_class(seq)
        assert d["red"] == 1
        assert d["black"] == 3

    def test_init_pair_sequence(self):
        seq = (("red", 1), ("black", 3))
        d = self.dict_class(seq)
        assert d["red"] == 1
        assert d["black"] == 3

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
        assert d["red"] == 1
        assert d["black"] == 3

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
        assert d["red"] == 1
        assert d["black"] == 3

    def test_caseless(self):
        d = self.dict_class()
        d["key_Lower"] = 1
        assert d["KEy_loWer"] == 1
        assert d.get("KEy_loWer") == 1

        d["KEY_LOWER"] = 3
        assert d["key_Lower"] == 3
        assert d.get("key_Lower") == 3

    def test_delete(self):
        d = self.dict_class({"key_lower": 1})
        del d["key_LOWER"]
        with pytest.raises(KeyError):
            d["key_LOWER"]
        with pytest.raises(KeyError):
            d["key_lower"]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_getdefault(self):
        d = CaselessDict()
        assert d.get("c", 5) == 5
        d["c"] = 10
        assert d.get("c", 5) == 10

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_setdefault(self):
        d = CaselessDict({"a": 1, "b": 2})

        r = d.setdefault("A", 5)
        assert r == 1
        assert d["A"] == 1

        r = d.setdefault("c", 5)
        assert r == 5
        assert d["C"] == 5

    def test_fromkeys(self):
        keys = ("a", "b")

        d = self.dict_class.fromkeys(keys)
        assert d["A"] is None
        assert d["B"] is None

        d = self.dict_class.fromkeys(keys, 1)
        assert d["A"] == 1
        assert d["B"] == 1

        instance = self.dict_class()
        d = instance.fromkeys(keys)
        assert d["A"] is None
        assert d["B"] is None

        d = instance.fromkeys(keys, 1)
        assert d["A"] == 1
        assert d["B"] == 1

    def test_contains(self):
        d = self.dict_class()
        d["a"] = 1
        assert "A" in d

    def test_pop(self):
        d = self.dict_class()
        d["a"] = 1
        assert d.pop("A") == 1
        with pytest.raises(KeyError):
            d.pop("A")

    def test_normkey(self):
        class MyDict(self.dict_class):
            def _normkey(self, key):
                return key.title()

            normkey = _normkey  # deprecated CaselessDict class

        d = MyDict()
        d["key-one"] = 2
        assert list(d.keys()) == ["Key-One"]

    def test_normvalue(self):
        class MyDict(self.dict_class):
            def _normvalue(self, value):
                if value is not None:
                    return value + 1
                return None

            normvalue = _normvalue  # deprecated CaselessDict class

        d = MyDict({"key": 1})
        assert d["key"] == 2
        assert d.get("key") == 2

        d = MyDict()
        d["key"] = 1
        assert d["key"] == 2
        assert d.get("key") == 2

        d = MyDict()
        d.setdefault("key", 1)
        assert d["key"] == 2
        assert d.get("key") == 2

        d = MyDict()
        d.update({"key": 1})
        assert d["key"] == 2
        assert d.get("key") == 2

        d = MyDict.fromkeys(("key",), 1)
        assert d["key"] == 2
        assert d.get("key") == 2

    def test_copy(self):
        h1 = self.dict_class({"header1": "value"})
        h2 = copy.copy(h1)
        assert isinstance(h2, self.dict_class)
        assert h1 == h2
        assert h1.get("header1") == h2.get("header1")
        assert h1.get("header1") == h2.get("HEADER1")
        h3 = h1.copy()
        assert isinstance(h3, self.dict_class)
        assert h1 == h3
        assert h1.get("header1") == h3.get("header1")
        assert h1.get("header1") == h3.get("HEADER1")


class TestCaseInsensitiveDict(CaseInsensitiveDictBase):
    dict_class = CaseInsensitiveDict

    def test_repr(self):
        d1 = self.dict_class({"foo": "bar"})
        assert repr(d1) == "<CaseInsensitiveDict: {'foo': 'bar'}>"
        d2 = self.dict_class({"AsDf": "QwErTy", "FoO": "bAr"})
        assert repr(d2) == "<CaseInsensitiveDict: {'AsDf': 'QwErTy', 'FoO': 'bAr'}>"

    def test_iter(self):
        d = self.dict_class({"AsDf": "QwErTy", "FoO": "bAr"})
        iterkeys = iter(d)
        assert isinstance(iterkeys, Iterator)
        assert list(iterkeys) == ["AsDf", "FoO"]


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestCaselessDict(CaseInsensitiveDictBase):
    dict_class = CaselessDict

    def test_deprecation_message(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.filterwarnings("always", category=ScrapyDeprecationWarning)
            self.dict_class({"foo": "bar"})

            assert len(caught) == 1
            assert issubclass(caught[0].category, ScrapyDeprecationWarning)
            assert (
                str(caught[0].message)
                == "scrapy.utils.datatypes.CaselessDict is deprecated,"
                " please use scrapy.utils.datatypes.CaseInsensitiveDict instead"
            )


class TestSequenceExclude:
    def test_list(self):
        seq = [1, 2, 3]
        d = SequenceExclude(seq)
        assert 0 in d
        assert 4 in d
        assert 2 not in d

    def test_range(self):
        seq = range(10, 20)
        d = SequenceExclude(seq)
        assert 5 in d
        assert 20 in d
        assert 15 not in d

    def test_range_step(self):
        seq = range(10, 20, 3)
        d = SequenceExclude(seq)
        are_not_in = [v for v in range(10, 20, 3) if v in d]
        assert are_not_in == []

        are_not_in = [v for v in range(10, 20) if v in d]
        assert are_not_in == [11, 12, 14, 15, 17, 18]

    def test_string_seq(self):
        seq = "cde"
        d = SequenceExclude(seq)
        chars = "".join(v for v in "abcdefg" if v in d)
        assert chars == "abfg"

    def test_stringset_seq(self):
        seq = set("cde")
        d = SequenceExclude(seq)
        chars = "".join(v for v in "abcdefg" if v in d)
        assert chars == "abfg"

    def test_set(self):
        """Anything that is not in the supplied sequence will evaluate as 'in' the container."""
        seq = {-3, "test", 1.1}
        d = SequenceExclude(seq)
        assert 0 in d
        assert "foo" in d
        assert 3.14 in d
        assert set("bar") in d

        # supplied sequence is a set, so checking for list (non)inclusion fails
        with pytest.raises(TypeError):
            ["a", "b", "c"] in d  # noqa: B015

        for v in [-3, "test", 1.1]:
            assert v not in d


class TestLocalCache:
    def test_cache_with_limit(self):
        cache = LocalCache(limit=2)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        assert len(cache) == 2
        assert "a" not in cache
        assert "b" in cache
        assert "c" in cache
        assert cache["b"] == 2
        assert cache["c"] == 3

    def test_cache_without_limit(self):
        maximum = 10**4
        cache = LocalCache()
        for x in range(maximum):
            cache[str(x)] = x
        assert len(cache) == maximum
        for x in range(maximum):
            assert str(x) in cache
            assert cache[str(x)] == x


class TestLocalWeakReferencedCache:
    def test_cache_with_limit(self):
        cache = LocalWeakReferencedCache(limit=2)
        r1 = Request("https://example.org")
        r2 = Request("https://example.com")
        r3 = Request("https://example.net")
        cache[r1] = 1
        cache[r2] = 2
        cache[r3] = 3
        assert len(cache) == 2
        assert r1 not in cache
        assert r2 in cache
        assert r3 in cache
        assert cache[r1] is None
        assert cache[r2] == 2
        assert cache[r3] == 3
        del r2

        # PyPy takes longer to collect dead references
        garbage_collect()

        assert len(cache) == 1

    def test_cache_non_weak_referenceable_objects(self):
        cache = LocalWeakReferencedCache()
        k1 = None
        k2 = 1
        k3 = [1, 2, 3]
        cache[k1] = 1
        cache[k2] = 2
        cache[k3] = 3
        assert k1 not in cache
        assert k2 not in cache
        assert k3 not in cache
        assert len(cache) == 0

    def test_cache_without_limit(self):
        max = 10**4
        cache = LocalWeakReferencedCache()
        refs = []
        for x in range(max):
            refs.append(Request(f"https://example.org/{x}"))
            cache[refs[-1]] = x
        assert len(cache) == max
        for i, r in enumerate(refs):
            assert r in cache
            assert cache[r] == i
        del r  # delete reference to the last object in the list  # pylint: disable=undefined-loop-variable

        # delete half of the objects, make sure that is reflected in the cache
        for _ in range(max // 2):
            refs.pop()

        # PyPy takes longer to collect dead references
        garbage_collect()

        assert len(cache) == max // 2
        for i, r in enumerate(refs):
            assert r in cache
            assert cache[r] == i
