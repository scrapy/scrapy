import unittest

from scrapy.contrib_exp.newitem import *


class NewItemTest(unittest.TestCase):

    def test_simple(self):
        class TestItem(Item):
            name = StringField()

        i = TestItem()
        i.name = 'name'
        assert i.name == 'name'

