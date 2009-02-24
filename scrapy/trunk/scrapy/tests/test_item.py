import unittest

from scrapy.item import ScrapedItem

class ItemTestCase(unittest.TestCase):

    def test_item(self):
        
        class MyItem(ScrapedItem):
            pass

        item = MyItem()
        self.assertEqual(repr(item), 'MyItem({})')

        item = ScrapedItem({'key': 'value'})
        self.assertEqual(item.key, 'value')

        self.assertRaises(TypeError, ScrapedItem, 10)

if __name__ == "__main__":
    unittest.main()
