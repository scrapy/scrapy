# -*- coding: utf8 -*-
import unittest

from scrapy.contrib.item import RobustScrapedItem

class MyItem(RobustScrapedItem):
    ATTRIBUTES = {
        'guid': basestring,
        'name': basestring,
        'children': [basestring],
        'age': int,
        'alive': bool,
    }

class RobustScrapedItemTestCase(unittest.TestCase):
    def setUp(self):
        self.item = MyItem()

    def test_attribute_basic(self):
        self.assertRaises(ValueError, self.item.attribute, 'foo')
        self.assertRaises(AttributeError, self.item.attribute, 'foo', 'something')

        self.item.attribute('name', 'John')
        self.assertEqual(self.item.name, 'John')

        self.assertRaises(TypeError, self.item.attribute, 'children', ['Peter'])
        self.item.attribute('children', *['Peter'])
        self.assertEqual(self.item.children, ['Peter'])

        self.item.attribute('age', 40)
        self.assertEqual(self.item.age, 40)

        self.item.attribute('alive', False)
        self.assertEqual(self.item.alive, False)

    def test_attribute_override(self):
        self.item.attribute('name', 'John')
        self.item.attribute('name', 'Charlie')
        self.assertEqual(self.item.name, 'John')

        self.item.attribute('name', 'Charlie', override=True)
        self.assertEqual(self.item.name, 'Charlie')

    def test_attribute_add(self):
        self.item.attribute('name', 'John')
        self.assertRaises(NotImplementedError, self.item.attribute, 'name', 'Doe', add=True)

        self.item.attribute('children', *['Ken', 'Tom'])
        self.item.attribute('children', 'Bobby')
        self.item.attribute('children', 'Jimmy', add=True)
        self.assertEqual(self.item.children, ['Ken', 'Tom', 'Jimmy'])

        self.item.attribute('children', 'Johnny', 'Rodrigo', add=True)
        self.assertEqual(self.item.children, ['Ken', 'Tom', 'Jimmy', 'Johnny', 'Rodrigo'])

