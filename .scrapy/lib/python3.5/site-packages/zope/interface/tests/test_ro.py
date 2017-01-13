##############################################################################
#
# Copyright (c) 2014 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Resolution ordering utility tests"""
import unittest


class Test__mergeOrderings(unittest.TestCase):

    def _callFUT(self, orderings):
        from zope.interface.ro import _mergeOrderings
        return _mergeOrderings(orderings)

    def test_empty(self):
        self.assertEqual(self._callFUT([]), [])

    def test_single(self):
        self.assertEqual(self._callFUT(['a', 'b', 'c']), ['a', 'b', 'c'])

    def test_w_duplicates(self):
        self.assertEqual(self._callFUT([['a'], ['b', 'a']]), ['b', 'a'])

    def test_suffix_across_multiple_duplicats(self):
        O1 = ['x', 'y', 'z']
        O2 = ['q', 'z']
        O3 = [1, 3, 5]
        O4 = ['z']
        self.assertEqual(self._callFUT([O1, O2, O3, O4]),
                         ['x', 'y', 'q', 1, 3, 5, 'z'])


class Test__flatten(unittest.TestCase):

    def _callFUT(self, ob):
        from zope.interface.ro import _flatten
        return _flatten(ob)

    def test_w_empty_bases(self):
        class Foo(object):
            pass
        foo = Foo()
        foo.__bases__ = ()
        self.assertEqual(self._callFUT(foo), [foo])

    def test_w_single_base(self):
        class Foo(object):
            pass
        self.assertEqual(self._callFUT(Foo), [Foo, object])

    def test_w_bases(self):
        class Foo(object):
            pass
        class Bar(Foo):
            pass
        self.assertEqual(self._callFUT(Bar), [Bar, Foo, object])

    def test_w_diamond(self):
        class Foo(object):
            pass
        class Bar(Foo):
            pass
        class Baz(Foo):
            pass
        class Qux(Bar, Baz):
            pass
        self.assertEqual(self._callFUT(Qux),
                         [Qux, Bar, Foo, object, Baz, Foo, object])


class Test_ro(unittest.TestCase):

    def _callFUT(self, ob):
        from zope.interface.ro import ro
        return ro(ob)

    def test_w_empty_bases(self):
        class Foo(object):
            pass
        foo = Foo()
        foo.__bases__ = ()
        self.assertEqual(self._callFUT(foo), [foo])

    def test_w_single_base(self):
        class Foo(object):
            pass
        self.assertEqual(self._callFUT(Foo), [Foo, object])

    def test_w_bases(self):
        class Foo(object):
            pass
        class Bar(Foo):
            pass
        self.assertEqual(self._callFUT(Bar), [Bar, Foo, object])

    def test_w_diamond(self):
        class Foo(object):
            pass
        class Bar(Foo):
            pass
        class Baz(Foo):
            pass
        class Qux(Bar, Baz):
            pass
        self.assertEqual(self._callFUT(Qux),
                         [Qux, Bar, Baz, Foo, object])
