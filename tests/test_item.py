import sys
import unittest
from unittest import mock
from warnings import catch_warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.item import ABCMeta, _BaseItem, BaseItem, DictItem, Field, Item, ItemMeta


PY36_PLUS = (sys.version_info.major >= 3) and (sys.version_info.minor >= 6)


class ItemTest(unittest.TestCase):

    def assertSortedEqual(self, first, second, msg=None):
        return self.assertEqual(sorted(first), sorted(second), msg)

    def test_simple(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        i['name'] = u'name'
        self.assertEqual(i['name'], u'name')

    def test_init(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        self.assertRaises(KeyError, i.__getitem__, 'name')

        i2 = TestItem(name=u'john doe')
        self.assertEqual(i2['name'], u'john doe')

        i3 = TestItem({'name': u'john doe'})
        self.assertEqual(i3['name'], u'john doe')

        i4 = TestItem(i3)
        self.assertEqual(i4['name'], u'john doe')

        self.assertRaises(KeyError, TestItem, {'name': u'john doe',
                                               'other': u'foo'})

    def test_invalid_field(self):
        class TestItem(Item):
            pass

        i = TestItem()
        self.assertRaises(KeyError, i.__setitem__, 'field', 'text')
        self.assertRaises(KeyError, i.__getitem__, 'field')

    def test_repr(self):
        class TestItem(Item):
            name = Field()
            number = Field()

        i = TestItem()
        i['name'] = u'John Doe'
        i['number'] = 123
        itemrepr = repr(i)

        self.assertEqual(itemrepr,
                         "{'name': 'John Doe', 'number': 123}")

        i2 = eval(itemrepr)
        self.assertEqual(i2['name'], 'John Doe')
        self.assertEqual(i2['number'], 123)

    def test_private_attr(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        i._private = 'test'
        self.assertEqual(i._private, 'test')

    def test_raise_getattr(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        self.assertRaises(AttributeError, getattr, i, 'name')

    def test_raise_setattr(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        self.assertRaises(AttributeError, setattr, i, 'name', 'john')

    def test_custom_methods(self):
        class TestItem(Item):
            name = Field()

            def get_name(self):
                return self['name']

            def change_name(self, name):
                self['name'] = name

        i = TestItem()
        self.assertRaises(KeyError, i.get_name)
        i['name'] = u'lala'
        self.assertEqual(i.get_name(), u'lala')
        i.change_name(u'other')
        self.assertEqual(i.get_name(), 'other')

    def test_metaclass(self):
        class TestItem(Item):
            name = Field()
            keys = Field()
            values = Field()

        i = TestItem()
        i['name'] = u'John'
        self.assertEqual(list(i.keys()), ['name'])
        self.assertEqual(list(i.values()), ['John'])

        i['keys'] = u'Keys'
        i['values'] = u'Values'
        self.assertSortedEqual(list(i.keys()), ['keys', 'values', 'name'])
        self.assertSortedEqual(list(i.values()), [u'Keys', u'Values', u'John'])

    def test_metaclass_with_fields_attribute(self):
        class TestItem(Item):
            fields = {'new': Field(default='X')}

        item = TestItem(new=u'New')
        self.assertSortedEqual(list(item.keys()), ['new'])
        self.assertSortedEqual(list(item.values()), [u'New'])

    def test_metaclass_inheritance(self):
        class ParentItem(Item):
            name = Field()
            keys = Field()
            values = Field()

        class TestItem(ParentItem):
            keys = Field()

        i = TestItem()
        i['keys'] = 3
        self.assertEqual(list(i.keys()), ['keys'])
        self.assertEqual(list(i.values()), [3])

    def test_metaclass_multiple_inheritance_simple(self):
        class A(Item):
            fields = {'load': Field(default='A')}
            save = Field(default='A')

        class B(A):
            pass

        class C(Item):
            fields = {'load': Field(default='C')}
            save = Field(default='C')

        class D(B, C):
            pass

        item = D(save='X', load='Y')
        self.assertEqual(item['save'], 'X')
        self.assertEqual(item['load'], 'Y')
        self.assertEqual(D.fields, {'load': {'default': 'A'}, 'save': {'default': 'A'}})

        # D class inverted
        class E(C, B):
            pass

        self.assertEqual(E(save='X')['save'], 'X')
        self.assertEqual(E(load='X')['load'], 'X')
        self.assertEqual(E.fields, {'load': {'default': 'C'}, 'save': {'default': 'C'}})

    def test_metaclass_multiple_inheritance_diamond(self):
        class A(Item):
            fields = {'update': Field(default='A')}
            save = Field(default='A')
            load = Field(default='A')

        class B(A):
            pass

        class C(A):
            fields = {'update': Field(default='C')}
            save = Field(default='C')

        class D(B, C):
            fields = {'update': Field(default='D')}
            load = Field(default='D')

        self.assertEqual(D(save='X')['save'], 'X')
        self.assertEqual(D(load='X')['load'], 'X')
        self.assertEqual(
            D.fields,
            {'save': {'default': 'C'}, 'load': {'default': 'D'}, 'update': {'default': 'D'}})

        # D class inverted
        class E(C, B):
            load = Field(default='E')

        self.assertEqual(E(save='X')['save'], 'X')
        self.assertEqual(E(load='X')['load'], 'X')
        self.assertEqual(
            E.fields,
            {'save': {'default': 'C'}, 'load': {'default': 'E'}, 'update': {'default': 'C'}})

    def test_metaclass_multiple_inheritance_without_metaclass(self):
        class A(Item):
            fields = {'load': Field(default='A')}
            save = Field(default='A')

        class B(A):
            pass

        class C:
            fields = {'load': Field(default='C')}
            not_allowed = Field(default='not_allowed')
            save = Field(default='C')

        class D(B, C):
            pass

        self.assertRaises(KeyError, D, not_allowed='value')
        self.assertEqual(D(save='X')['save'], 'X')
        self.assertEqual(D.fields, {'save': {'default': 'A'}, 'load': {'default': 'A'}})

        # D class inverted
        class E(C, B):
            pass

        self.assertRaises(KeyError, E, not_allowed='value')
        self.assertEqual(E(save='X')['save'], 'X')
        self.assertEqual(E.fields, {'save': {'default': 'A'}, 'load': {'default': 'A'}})

    def test_to_dict(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        i['name'] = u'John'
        self.assertEqual(dict(i), {'name': u'John'})

    def test_copy(self):
        class TestItem(Item):
            name = Field()
        item = TestItem({'name': 'lower'})
        copied_item = item.copy()
        self.assertNotEqual(id(item), id(copied_item))
        copied_item['name'] = copied_item['name'].upper()
        self.assertNotEqual(item['name'], copied_item['name'])

    def test_deepcopy(self):
        class TestItem(Item):
            tags = Field()
        item = TestItem({'tags': ['tag1']})
        copied_item = item.deepcopy()
        item['tags'].append('tag2')
        assert item['tags'] != copied_item['tags']

    def test_dictitem_deprecation_warning(self):
        """Make sure the DictItem deprecation warning is not issued for
        Item"""
        with catch_warnings(record=True) as warnings:
            Item()
            self.assertEqual(len(warnings), 0)

            class SubclassedItem(Item):
                pass
            SubclassedItem()
            self.assertEqual(len(warnings), 0)


class ItemMetaTest(unittest.TestCase):

    def test_new_method_propagates_classcell(self):
        new_mock = mock.Mock(side_effect=ABCMeta.__new__)
        base = ItemMeta.__bases__[0]

        with mock.patch.object(base, '__new__', new_mock):

            class MyItem(Item):
                if not PY36_PLUS:
                    # This attribute is an internal attribute in Python 3.6+
                    # and must be propagated properly. See
                    # https://docs.python.org/3.6/reference/datamodel.html#creating-the-class-object
                    # In <3.6, we add a dummy attribute just to ensure the
                    # __new__ method propagates it correctly.
                    __classcell__ = object()

                def f(self):
                    # For rationale of this see:
                    # https://github.com/python/cpython/blob/ee1a81b77444c6715cbe610e951c655b6adab88b/Lib/test/test_super.py#L222
                    return __class__  # noqa  https://github.com/scrapy/scrapy/issues/2836

            MyItem()

        (first_call, second_call) = new_mock.call_args_list[-2:]

        mcs, class_name, bases, attrs = first_call[0]
        assert '__classcell__' not in attrs
        mcs, class_name, bases, attrs = second_call[0]
        assert '__classcell__' in attrs


class ItemMetaClassCellRegression(unittest.TestCase):

    def test_item_meta_classcell_regression(self):
        class MyItem(Item, metaclass=ItemMeta):
            def __init__(self, *args, **kwargs):
                # This call to super() trigger the __classcell__ propagation
                # requirement. When not done properly raises an error:
                # TypeError: __class__ set to <class '__main__.MyItem'>
                # defining 'MyItem' as <class '__main__.MyItem'>
                super().__init__(*args, **kwargs)


class DictItemTest(unittest.TestCase):

    def test_deprecation_warning(self):
        with catch_warnings(record=True) as warnings:
            DictItem()
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, ScrapyDeprecationWarning)
        with catch_warnings(record=True) as warnings:
            class SubclassedDictItem(DictItem):
                pass
            SubclassedDictItem()
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, ScrapyDeprecationWarning)


class BaseItemTest(unittest.TestCase):

    def test_isinstance_check(self):

        class SubclassedBaseItem(BaseItem):
            pass

        class SubclassedItem(Item):
            pass

        self.assertTrue(isinstance(BaseItem(), BaseItem))
        self.assertTrue(isinstance(SubclassedBaseItem(), BaseItem))
        self.assertTrue(isinstance(Item(), BaseItem))
        self.assertTrue(isinstance(SubclassedItem(), BaseItem))

        # make sure internal checks using private _BaseItem class succeed
        self.assertTrue(isinstance(BaseItem(), _BaseItem))
        self.assertTrue(isinstance(SubclassedBaseItem(), _BaseItem))
        self.assertTrue(isinstance(Item(), _BaseItem))
        self.assertTrue(isinstance(SubclassedItem(), _BaseItem))

    def test_deprecation_warning(self):
        """
        Make sure deprecation warnings are logged whenever BaseItem is used,
        either instantiated or in an isinstance check
        """
        with catch_warnings(record=True) as warnings:
            BaseItem()
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, ScrapyDeprecationWarning)

        with catch_warnings(record=True) as warnings:

            class SubclassedBaseItem(BaseItem):
                pass

            SubclassedBaseItem()
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, ScrapyDeprecationWarning)

        with catch_warnings(record=True) as warnings:
            self.assertFalse(isinstance("foo", BaseItem))
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, ScrapyDeprecationWarning)

        with catch_warnings(record=True) as warnings:
            self.assertTrue(isinstance(BaseItem(), BaseItem))
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, ScrapyDeprecationWarning)


class ItemNoDeprecationWarningTest(unittest.TestCase):
    def test_no_deprecation_warning(self):
        """
        Make sure deprecation warnings are NOT logged whenever BaseItem subclasses are used.
        """
        class SubclassedItem(Item):
            pass

        with catch_warnings(record=True) as warnings:
            Item()
            SubclassedItem()
            _BaseItem()
            self.assertFalse(isinstance("foo", _BaseItem))
            self.assertFalse(isinstance("foo", Item))
            self.assertFalse(isinstance("foo", SubclassedItem))
            self.assertTrue(isinstance(_BaseItem(), _BaseItem))
            self.assertTrue(isinstance(Item(), Item))
            self.assertTrue(isinstance(SubclassedItem(), SubclassedItem))
            self.assertEqual(len(warnings), 0)


if __name__ == "__main__":
    unittest.main()
