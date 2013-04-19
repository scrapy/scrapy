import unittest

from scrapy.item import Item, Field


class ItemTest(unittest.TestCase):

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
                         "{'name': u'John Doe', 'number': 123}")

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
        self.assertEqual(i.keys(), ['name'])
        self.assertEqual(i.values(), ['John'])

        i['keys'] = u'Keys'
        i['values'] = u'Values'
        self.assertEqual(i.keys(), ['keys', 'values', 'name'])
        self.assertEqual(i.values(), [u'Keys', u'Values', u'John'])

    def test_metaclass_inheritance(self):
        class BaseItem(Item):
            name = Field()
            keys = Field()
            values = Field()

        class TestItem(BaseItem):
            keys = Field()

        i = TestItem()
        i['keys'] = 3
        self.assertEqual(i.keys(), ['keys'])
        self.assertEqual(i.values(), [3])

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
