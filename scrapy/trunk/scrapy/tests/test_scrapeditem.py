# -*- coding: utf8 -*-
import unittest

from scrapy.item.models import ScrapedItem
from scrapy.item.adaptors import AdaptorPipe
from scrapy.contrib import adaptors

class ScrapedItemTestCase(unittest.TestCase):
    def setUp(self):
        self.item = ScrapedItem()

    def test_attribute_basic(self):
        self.item.attribute('name', 'John')
        self.assertEqual(self.item.name, 'John')

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

        self.item.attribute('name', 'Smith', add=' ')
        self.assertEqual(self.item.name, 'JohnDoe Smith')

        self.item.attribute('children', ['Ken', 'Tom'])
        self.item.attribute('children', 'Bobby')
        self.item.attribute('children', 'Jimmy', add=True)
        self.assertEqual(self.item.children, ['Ken', 'Tom', 'Jimmy'])

        self.item.attribute('children', ['Johnny', 'Rodrigo'], add=True)
        self.assertEqual(self.item.children, ['Ken', 'Tom', 'Jimmy', 'Johnny', 'Rodrigo'])

    def test_set_adaptors(self):
        self.assertEqual(self.item._adaptors_dict, {})

        delist = adaptors.Delist()
        self.item.set_adaptors({'name': [adaptors.extract, delist]})
        self.assertEqual(self.item._adaptors_dict, {'name': [adaptors.extract, delist]})

        self.item.set_adaptors({'description': [adaptors.extract]})
        self.assertEqual(self.item._adaptors_dict, {'description': [adaptors.extract]})

    def test_set_attrib_adaptors(self):
        self.assertEqual(self.item._adaptors_dict, {})

        self.item.set_attrib_adaptors('name', [adaptors.extract, adaptors.strip])
        self.assertEqual(self.item._adaptors_dict['name'],
            AdaptorPipe([adaptors.extract, adaptors.strip]))

        unquote = adaptors.Unquote()
        self.item.set_attrib_adaptors('name', [adaptors.extract, unquote])
        self.assertEqual(self.item._adaptors_dict['name'],
            AdaptorPipe([adaptors.extract, unquote]))

    def test_add_adaptor(self):
        self.assertEqual(self.item._adaptors_dict, {})

        self.item.add_adaptor('name', adaptors.strip)
        self.assertEqual(self.item._adaptors_dict['name'], [adaptors.strip])
        self.item.add_adaptor('name', adaptors.extract, position=0)
        self.assertEqual(self.item._adaptors_dict['name'], [adaptors.extract, adaptors.strip])

