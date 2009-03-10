import unittest

from scrapy.contrib_exp.newitem import *


class NewItemTest(unittest.TestCase):

    def test_simple(self):
        class TestItem(Item):
            name = StringField()

        i = TestItem()
        i.name = 'name'
        assert i.name == 'name'

    def test_multi(self):
        class TestMultiItem(Item):
            name = StringField()
            names = MultiValuedField(StringField)

        i = TestMultiItem()
        i.name = 'name'
        i.names = ['name1', 'name2']
        assert i.names == ['name1', 'name2']
