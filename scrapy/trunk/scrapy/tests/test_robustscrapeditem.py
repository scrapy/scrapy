# -*- coding: utf8 -*-
import unittest

from scrapy.contrib.item import RobustScrapedItem
from scrapy.item.adaptors import AdaptorPipe, AdaptorFunc
from scrapy.contrib_exp import adaptors
from scrapy.core.exceptions import UsageError

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
        self.assertRaises(UsageError, self.item.attribute, 'foo')
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

        self.item.attribute('name', 'Doe', add=True)
        self.assertEqual(self.item.name, 'JohnDoe')

        self.item.attribute('children', *['Ken', 'Tom'])
        self.item.attribute('children', 'Bobby')
        self.item.attribute('children', 'Jimmy', add=True)
        self.assertEqual(self.item.children, ['Ken', 'Tom', 'Jimmy'])

        self.item.attribute('children', 'Johnny', 'Rodrigo', add=True)
        self.assertEqual(self.item.children, ['Ken', 'Tom', 'Jimmy', 'Johnny', 'Rodrigo'])

    def test_set_adaptors(self):
        self.assertEqual(self.item._adaptors_dict, {})

        delist = adaptors.Delist()
        self.item.set_adaptors({'name': [adaptors.extract, delist]})
        self.assertTrue(isinstance(self.item._adaptors_dict['name'], AdaptorPipe))
        self.assertEqual(self.item._adaptors_dict['name'][0].name, "extract")
        self.assertEqual(self.item._adaptors_dict['name'][1].name, "Delist")

        self.item.set_adaptors({'description': [adaptors.extract]})
        self.assertEqual(self.item._adaptors_dict['description'][0].name, "extract")

    def test_set_attrib_adaptors(self):
        self.assertEqual(self.item._adaptors_dict, {})

        self.item.set_attrib_adaptors('name', [adaptors.extract, adaptors.strip])
        self.assertTrue(isinstance(self.item._adaptors_dict['name'], AdaptorPipe))
        self.assertEqual(self.item._adaptors_dict['name'][0].name, "extract")
        self.assertEqual(self.item._adaptors_dict['name'][1].name, "strip")

        unquote = adaptors.Unquote()
        self.item.set_attrib_adaptors('name', [adaptors.extract, unquote])
        self.assertTrue(isinstance(self.item._adaptors_dict['name'], AdaptorPipe))
        self.assertEqual(self.item._adaptors_dict['name'][0].name, "extract")
        self.assertEqual(self.item._adaptors_dict['name'][1].name, "Unquote")

    def test_add_adaptor(self):
        self.assertEqual(self.item._adaptors_dict, {})

        self.item.add_adaptor('name', adaptors.strip)
        self.assertEqual(self.item._adaptors_dict['name'][0].name, "strip")
        self.item.add_adaptor('name', adaptors.extract, position=0)
        self.assertEqual(self.item._adaptors_dict['name'][0].name, "extract")
        self.assertEqual(self.item._adaptors_dict['name'][1].name, "strip")
