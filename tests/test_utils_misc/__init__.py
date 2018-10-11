import sys
import os
import unittest

from scrapy.item import Item, Field
from scrapy.utils.misc import arg_to_iter, create_instance, load_object, walk_modules

from tests import mock

__doctests__ = ['scrapy.utils.misc']

class UtilsMiscTestCase(unittest.TestCase):

    def test_load_object(self):
        obj = load_object('scrapy.utils.misc.load_object')
        assert obj is load_object
        self.assertRaises(ImportError, load_object, 'nomodule999.mod.function')
        self.assertRaises(NameError, load_object, 'scrapy.utils.misc.load_object999')

    def test_walk_modules(self):
        mods = walk_modules('tests.test_utils_misc.test_walk_modules')
        expected = [
            'tests.test_utils_misc.test_walk_modules',
            'tests.test_utils_misc.test_walk_modules.mod',
            'tests.test_utils_misc.test_walk_modules.mod.mod0',
            'tests.test_utils_misc.test_walk_modules.mod1',
        ]
        self.assertEqual(set([m.__name__ for m in mods]), set(expected))

        mods = walk_modules('tests.test_utils_misc.test_walk_modules.mod')
        expected = [
            'tests.test_utils_misc.test_walk_modules.mod',
            'tests.test_utils_misc.test_walk_modules.mod.mod0',
        ]
        self.assertEqual(set([m.__name__ for m in mods]), set(expected))

        mods = walk_modules('tests.test_utils_misc.test_walk_modules.mod1')
        expected = [
            'tests.test_utils_misc.test_walk_modules.mod1',
        ]
        self.assertEqual(set([m.__name__ for m in mods]), set(expected))

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
            self.assertEqual(set([m.__name__ for m in mods]), set(expected))
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

    def test_create_instance(self):
        settings = mock.MagicMock()
        crawler = mock.MagicMock(spec_set=['settings'])
        args = (True, 100.)
        kwargs = {'key': 'val'}

        def _test_with_settings(mock, settings):
            create_instance(mock, settings, None, *args, **kwargs)
            if hasattr(mock, 'from_crawler'):
                self.assertEqual(mock.from_crawler.call_count, 0)
            if hasattr(mock, 'from_settings'):
                mock.from_settings.assert_called_once_with(settings, *args,
                                                           **kwargs)
                self.assertEqual(mock.call_count, 0)
            else:
                mock.assert_called_once_with(*args, **kwargs)

        def _test_with_crawler(mock, settings, crawler):
            create_instance(mock, settings, crawler, *args, **kwargs)
            if hasattr(mock, 'from_crawler'):
                mock.from_crawler.assert_called_once_with(crawler, *args,
                                                          **kwargs)
                if hasattr(mock, 'from_settings'):
                    self.assertEqual(mock.from_settings.call_count, 0)
                self.assertEqual(mock.call_count, 0)
            elif hasattr(mock, 'from_settings'):
                mock.from_settings.assert_called_once_with(settings, *args,
                                                           **kwargs)
                self.assertEqual(mock.call_count, 0)
            else:
                mock.assert_called_once_with(*args, **kwargs)

        # Check usage of correct constructor using four mocks:
        #   1. with no alternative constructors
        #   2. with from_settings() constructor
        #   3. with from_crawler() constructor
        #   4. with from_settings() and from_crawler() constructor
        spec_sets = ([], ['from_settings'], ['from_crawler'],
                     ['from_settings', 'from_crawler'])
        for specs in spec_sets:
            m = mock.MagicMock(spec_set=specs)
            _test_with_settings(m, settings)
            m.reset_mock()
            _test_with_crawler(m, settings, crawler)

        # Check adoption of crawler settings
        m = mock.MagicMock(spec_set=['from_settings'])
        create_instance(m, None, crawler, *args, **kwargs)
        m.from_settings.assert_called_once_with(crawler.settings, *args,
                                                **kwargs)

        with self.assertRaises(ValueError):
            create_instance(m, None, None)

if __name__ == "__main__":
    unittest.main()
