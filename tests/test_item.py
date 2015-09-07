import unittest

from scrapy.item import Item, Field
import six


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

        if six.PY2:
            self.assertEqual(itemrepr,
                             "{'name': u'John Doe', 'number': 123}")
        else:
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
        class BaseItem(Item):
            name = Field()
            keys = Field()
            values = Field()

        class TestItem(BaseItem):
            keys = Field()

        i = TestItem()
        i['keys'] = 3
        self.assertEqual(list(i.keys()), ['keys'])
        self.assertEqual(list(i.values()), [3])

    def test_metaclass_multiple_inheritance_simple(self):
        class A(Item):
            fields = {'load': Field(default='A')}
            save = Field(default='A')

        class B(A): pass

        class C(Item):
            fields = {'load': Field(default='C')}
            save = Field(default='C')

        class D(B, C): pass

        item = D(save='X', load='Y')
        self.assertEqual(item['save'], 'X')
        self.assertEqual(item['load'], 'Y')
        self.assertEqual(D.fields, {'load': {'default': 'A'},
            'save': {'default': 'A'}})

        # D class inverted
        class E(C, B): pass

        self.assertEqual(E(save='X')['save'], 'X')
        self.assertEqual(E(load='X')['load'], 'X')
        self.assertEqual(E.fields, {'load': {'default': 'C'},
            'save': {'default': 'C'}})

    def test_metaclass_multiple_inheritance_diamond(self):
        class A(Item):
            fields = {'update': Field(default='A')}
            save = Field(default='A')
            load = Field(default='A')

        class B(A): pass

        class C(A):
            fields = {'update': Field(default='C')}
            save = Field(default='C')

        class D(B, C):
            fields = {'update': Field(default='D')}
            load = Field(default='D')

        self.assertEqual(D(save='X')['save'], 'X')
        self.assertEqual(D(load='X')['load'], 'X')
        self.assertEqual(D.fields, {'save': {'default': 'C'},
            'load': {'default': 'D'}, 'update': {'default': 'D'}})

        # D class inverted
        class E(C, B):
            load = Field(default='E')

        self.assertEqual(E(save='X')['save'], 'X')
        self.assertEqual(E(load='X')['load'], 'X')
        self.assertEqual(E.fields, {'save': {'default': 'C'},
            'load': {'default': 'E'}, 'update': {'default': 'C'}})

    def test_metaclass_multiple_inheritance_without_metaclass(self):
        class A(Item):
            fields = {'load': Field(default='A')}
            save = Field(default='A')

        class B(A): pass

        class C(object):
            fields = {'load': Field(default='C')}
            not_allowed = Field(default='not_allowed')
            save = Field(default='C')

        class D(B, C): pass

        self.assertRaises(KeyError, D, not_allowed='value')
        self.assertEqual(D(save='X')['save'], 'X')
        self.assertEqual(D.fields, {'save': {'default': 'A'},
            'load': {'default': 'A'}})

        # D class inverted
        class E(C, B): pass

        self.assertRaises(KeyError, E, not_allowed='value')
        self.assertEqual(E(save='X')['save'], 'X')
        self.assertEqual(E.fields, {'save': {'default': 'A'},
            'load': {'default': 'A'}})

    def test_to_dict(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        i['name'] = u'John'
        self.assertEqual(dict(i), {'name': u'John'})

    def test_copy(self):
        class TestItem(Item):
            name = Field()
        item = TestItem({'name':'lower'})
        copied_item = item.copy()
        self.assertNotEqual(id(item), id(copied_item))
        copied_item['name'] = copied_item['name'].upper()
        self.assertNotEqual(item['name'], copied_item['name'])


if __name__ == "__main__":
    unittest.main()
