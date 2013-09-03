import sys
import os
import unittest
from cStringIO import StringIO

from scrapy.item import Item, Field
from scrapy.utils.misc import load_object, arg_to_iter, walk_modules

__doctests__ = ['scrapy.utils.misc']

class UtilsMiscTestCase(unittest.TestCase):

    def test_load_object(self):
        obj = load_object('scrapy.utils.misc.load_object')
        assert obj is load_object
        self.assertRaises(ImportError, load_object, 'nomodule999.mod.function')
        self.assertRaises(NameError, load_object, 'scrapy.utils.misc.load_object999')

    def test_walk_modules(self):
        mods = walk_modules('scrapy.tests.test_utils_misc.test_walk_modules')
        expected = [
            'scrapy.tests.test_utils_misc.test_walk_modules',
            'scrapy.tests.test_utils_misc.test_walk_modules.mod',
            'scrapy.tests.test_utils_misc.test_walk_modules.mod.mod0',
            'scrapy.tests.test_utils_misc.test_walk_modules.mod1',
        ]
        self.assertEquals(set([m.__name__ for m in mods]), set(expected))

        mods = walk_modules('scrapy.tests.test_utils_misc.test_walk_modules.mod')
        expected = [
            'scrapy.tests.test_utils_misc.test_walk_modules.mod',
            'scrapy.tests.test_utils_misc.test_walk_modules.mod.mod0',
        ]
        self.assertEquals(set([m.__name__ for m in mods]), set(expected))

        mods = walk_modules('scrapy.tests.test_utils_misc.test_walk_modules.mod1')
        expected = [
            'scrapy.tests.test_utils_misc.test_walk_modules.mod1',
        ]
        self.assertEquals(set([m.__name__ for m in mods]), set(expected))

        self.assertRaises(ImportError, walk_modules, 'nomodule999')

    def test_walk_modules_egg(self):
        egg = os.path.join(os.path.dirname(__file__), 'test.egg')
        sys.path.append(egg)
        try:
            mods = walk_modules('testegg')
            expected = [
                'testegg.spiders',
                'testegg.spiders.a',
                'testegg.spiders.b',
                'testegg'
            ]
            self.assertEquals(set([m.__name__ for m in mods]), set(expected))
        finally:
            sys.path.remove(egg)

    def test_arg_to_iter(self):

        class TestItem(Item):
            name = Field()

        assert hasattr(arg_to_iter(None), '__iter__')
        assert hasattr(arg_to_iter(100), '__iter__')
        assert hasattr(arg_to_iter('lala'), '__iter__')
        assert hasattr(arg_to_iter([1, 2, 3]), '__iter__')
        assert hasattr(arg_to_iter(l for l in 'abcd'), '__iter__')

        self.assertEqual(list(arg_to_iter(None)), [])
        self.assertEqual(list(arg_to_iter('lala')), ['lala'])
        self.assertEqual(list(arg_to_iter(100)), [100])
        self.assertEqual(list(arg_to_iter(l for l in 'abc')), ['a', 'b', 'c'])
        self.assertEqual(list(arg_to_iter([1, 2, 3])), [1, 2, 3])
        self.assertEqual(list(arg_to_iter({'a':1})), [{'a': 1}])
        self.assertEqual(list(arg_to_iter(TestItem(name="john"))), [TestItem(name="john")])

if __name__ == "__main__":
    unittest.main()
