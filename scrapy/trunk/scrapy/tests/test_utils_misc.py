import unittest
from cStringIO import StringIO

from scrapy.utils.misc import hash_values, items_to_csv
from scrapy.core.exceptions import UsageError
from scrapy.item import ScrapedItem

class UtilsMiscTestCase(unittest.TestCase):
    def test_hash_values(self):
        self.assertEqual(hash_values('some', 'values', 'to', 'hash'),
                         'f37f5dc65beaaea35af05e16e26d439fd150c576')

        self.assertRaises(UsageError, hash_values, 'some', None, 'value')

    def test_items_to_csv(self):
        item_1 = ScrapedItem()
        item_1.attribute('_hidden', '543565')
        item_1.attribute('id', '3213')
        item_1.attribute('name', 'Item 1')
        item_1.attribute('description', 'Really cute item')
        item_1.attribute('url', 'http://dummyurl.com')

        item_2 = ScrapedItem()
        item_2.attribute('_hidden', 'lala')
        item_2.attribute('id', '1234')
        item_2.attribute('name', 'Item 2')
        item_2.attribute('description', 'This item rocks!')
        item_2.attribute('url', 'http://dummyurl.com/2')
        item_2.attribute('supplier', 'A random supplier')

        file = StringIO()
        items_to_csv(file, [item_1, item_2])
        file.reset()
        self.assertEqual(file.read(),
            '"description";"id";"name";"url"\r\n' +
            '"Really cute item";"3213";"Item 1";"http://dummyurl.com"\r\n' +
            '"This item rocks!";"1234";"Item 2";"http://dummyurl.com/2"\r\n')

        file = StringIO()
        items_to_csv(file, [item_2, item_1])
        file.reset()
        self.assertEqual(file.read(),
            '"description";"id";"name";"supplier";"url"\r\n' +
            '"This item rocks!";"1234";"Item 2";"A random supplier";"http://dummyurl.com/2"\r\n' +
            '"Really cute item";"3213";"Item 1";"";"http://dummyurl.com"\r\n')

        file = StringIO()
        items_to_csv(file, [])
        self.assertEqual(file.tell(), 0)

if __name__ == "__main__":
    unittest.main()
