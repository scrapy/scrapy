import functools
import gc
import operator
import platform
import unittest
from datetime import datetime
from itertools import count
from warnings import catch_warnings

from scrapy.utils.python import (
    memoizemethod_noargs, binary_is_text, equal_attributes,
    WeakKeyCache, get_func_args, to_bytes, to_unicode,
    without_none_values, MutableChain)


__doctests__ = ['scrapy.utils.python']


class MutableChainTest(unittest.TestCase):
    def test_mutablechain(self):
        m = MutableChain(range(2), [2, 3], (4, 5))
        m.extend(range(6, 7))
        m.extend([7, 8])
        m.extend([9, 10], (11, 12))
        self.assertEqual(next(m), 0)
        self.assertEqual(m.__next__(), 1)
        with catch_warnings(record=True) as warnings:
            self.assertEqual(m.next(), 2)
            self.assertEqual(len(warnings), 1)
            self.assertIn('scrapy.utils.python.MutableChain.__next__',
                          str(warnings[0].message))
        self.assertEqual(list(m), list(range(3, 13)))


class ToUnicodeTest(unittest.TestCase):
    def test_converting_an_utf8_encoded_string_to_unicode(self):
        self.assertEqual(to_unicode(b'lel\xc3\xb1e'), 'lel\xf1e')

    def test_converting_a_latin_1_encoded_string_to_unicode(self):
        self.assertEqual(to_unicode(b'lel\xf1e', 'latin-1'), 'lel\xf1e')

    def test_converting_a_unicode_to_unicode_should_return_the_same_object(self):
        self.assertEqual(to_unicode('\xf1e\xf1e\xf1e'), '\xf1e\xf1e\xf1e')

    def test_converting_a_strange_object_should_raise_TypeError(self):
        self.assertRaises(TypeError, to_unicode, 423)

    def test_errors_argument(self):
        self.assertEqual(
            to_unicode(b'a\xedb', 'utf-8', errors='replace'),
            'a\ufffdb'
        )


class ToBytesTest(unittest.TestCase):
    def test_converting_a_unicode_object_to_an_utf_8_encoded_string(self):
        self.assertEqual(to_bytes('\xa3 49'), b'\xc2\xa3 49')

    def test_converting_a_unicode_object_to_a_latin_1_encoded_string(self):
        self.assertEqual(to_bytes('\xa3 49', 'latin-1'), b'\xa3 49')

    def test_converting_a_regular_bytes_to_bytes_should_return_the_same_object(self):
        self.assertEqual(to_bytes(b'lel\xf1e'), b'lel\xf1e')

    def test_converting_a_strange_object_should_raise_TypeError(self):
        self.assertRaises(TypeError, to_bytes, unittest)

    def test_errors_argument(self):
        self.assertEqual(
            to_bytes('a\ufffdb', 'latin-1', errors='replace'),
            b'a?b'
        )


class MemoizedMethodTest(unittest.TestCase):
    def test_memoizemethod_noargs(self):
        class A:

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


class BinaryIsTextTest(unittest.TestCase):
    def test_binaryistext(self):
        assert binary_is_text(b"hello")

    def test_utf_16_strings_contain_null_bytes(self):
        assert binary_is_text("hello".encode('utf-16'))

    def test_one_with_encoding(self):
        assert binary_is_text(b"<div>Price \xa3</div>")

    def test_real_binary_bytes(self):
        assert not binary_is_text(b"\x02\xa3")


class UtilsPythonTestCase(unittest.TestCase):

    def test_equal_attributes(self):
        class Obj:
            pass

        a = Obj()
        b = Obj()
        # no attributes given return False
        self.assertFalse(equal_attributes(a, b, []))
        # not existent attributes
        self.assertFalse(equal_attributes(a, b, ['x', 'y']))

        a.x = 1
        b.x = 1
        # equal attribute
        self.assertTrue(equal_attributes(a, b, ['x']))

        b.y = 2
        # obj1 has no attribute y
        self.assertFalse(equal_attributes(a, b, ['x', 'y']))

        a.y = 2
        # equal attributes
        self.assertTrue(equal_attributes(a, b, ['x', 'y']))

        a.y = 1
        # differente attributes
        self.assertFalse(equal_attributes(a, b, ['x', 'y']))

        # test callable
        a.meta = {}
        b.meta = {}
        self.assertTrue(equal_attributes(a, b, ['meta']))

        # compare ['meta']['a']
        a.meta['z'] = 1
        b.meta['z'] = 1

        get_z = operator.itemgetter('z')
        get_meta = operator.attrgetter('meta')

        def compare_z(obj):
            return get_z(get_meta(obj))

        self.assertTrue(equal_attributes(a, b, [compare_z, 'x']))
        # fail z equality
        a.meta['z'] = 2
        self.assertFalse(equal_attributes(a, b, [compare_z, 'x']))

    def test_weakkeycache(self):
        class _Weakme:
            pass

        _values = count()
        wk = WeakKeyCache(lambda k: next(_values))
        k = _Weakme()
        v = wk[k]
        self.assertEqual(v, wk[k])
        self.assertNotEqual(v, wk[_Weakme()])
        self.assertEqual(v, wk[k])
        del k
        for _ in range(100):
            if wk._weakdict:
                gc.collect()
        self.assertFalse(len(wk._weakdict))

    def test_get_func_args(self):
        def f1(a, b, c):
            pass

        def f2(a, b=None, c=None):
            pass

        def f3(a, b=None, *, c=None):
            pass

        class A:
            def __init__(self, a, b, c):
                pass

            def method(self, a, b, c):
                pass

        class Callable:

            def __call__(self, a, b, c):
                pass

        a = A(1, 2, 3)
        cal = Callable()
        partial_f1 = functools.partial(f1, None)
        partial_f2 = functools.partial(f1, b=None)
        partial_f3 = functools.partial(partial_f2, None)

        self.assertEqual(get_func_args(f1), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(f2), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(f3), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(A), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(a.method), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(partial_f1), ['b', 'c'])
        self.assertEqual(get_func_args(partial_f2), ['a', 'c'])
        self.assertEqual(get_func_args(partial_f3), ['c'])
        self.assertEqual(get_func_args(cal), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(object), [])

        if platform.python_implementation() == 'CPython':
            # TODO: how do we fix this to return the actual argument names?
            self.assertEqual(get_func_args(str.split), [])
            self.assertEqual(get_func_args(" ".join), [])
            self.assertEqual(get_func_args(operator.itemgetter(2)), [])
        elif platform.python_implementation() == 'PyPy':
            self.assertEqual(get_func_args(str.split, stripself=True), ['sep', 'maxsplit'])
            self.assertEqual(get_func_args(operator.itemgetter(2), stripself=True), ['obj'])

            build_date = datetime.strptime(platform.python_build()[1], '%b %d %Y')
            if build_date >= datetime(2020, 4, 7):  # PyPy 3.6-v7.3.1
                self.assertEqual(get_func_args(" ".join, stripself=True), ['iterable'])
            else:
                self.assertEqual(get_func_args(" ".join, stripself=True), ['list'])

    def test_without_none_values(self):
        self.assertEqual(without_none_values([1, None, 3, 4]), [1, 3, 4])
        self.assertEqual(without_none_values((1, None, 3, 4)), (1, 3, 4))
        self.assertEqual(
            without_none_values({'one': 1, 'none': None, 'three': 3, 'four': 4}),
            {'one': 1, 'three': 3, 'four': 4})


if __name__ == "__main__":
    unittest.main()
