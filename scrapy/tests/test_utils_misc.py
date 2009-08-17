import unittest
from cStringIO import StringIO

from scrapy.utils.misc import items_to_csv, load_object, arg_to_iter
from scrapy.item import ScrapedItem

class UtilsMiscTestCase(unittest.TestCase):

    def test_items_to_csv(self):
        item_1 = ScrapedItem()
        item_1._hidden = '543565'
        item_1.id = '3213'
        item_1.name = 'Item 1'
        item_1.description = 'Really cute item'
        item_1.url = 'http://dummyurl.com'

        item_2 = ScrapedItem()
        item_2._hidden = 'lala'
        item_2.id = '1234'
        item_2.name = 'Item 2'
        item_2.description = 'This item rocks!'
        item_2.url = 'http://dummyurl.com/2'
        item_2.supplier = 'A random supplier'

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
        items_to_csv(file, [item_1, item_2], headers=['id', 'name'], delimiter=',')
        file.reset()
        self.assertEqual(file.read(),
            '"id","name"\r\n' +
            '"3213","Item 1"\r\n' +
            '"1234","Item 2"\r\n')

        file = StringIO()
        items_to_csv(file, [])
        self.assertEqual(file.tell(), 0)

    def test_load_object(self):
        obj = load_object('scrapy.utils.misc.load_object')
        assert obj is load_object
        self.assertRaises(ImportError, load_object, 'nomodule999.mod.function')
        self.assertRaises(NameError, load_object, 'scrapy.utils.misc.load_object999')

    def test_arg_to_iter(self):
        assert hasattr(arg_to_iter(None), '__iter__')
        assert hasattr(arg_to_iter(100), '__iter__')
        assert hasattr(arg_to_iter('lala'), '__iter__')
        assert hasattr(arg_to_iter([1,2,3]), '__iter__')
        assert hasattr(arg_to_iter(l for l in 'abcd'), '__iter__')

        self.assertEqual(list(arg_to_iter(None)), [])
        self.assertEqual(list(arg_to_iter('lala')), ['lala'])
        self.assertEqual(list(arg_to_iter(100)), [100])
        self.assertEqual(list(arg_to_iter(l for l in 'abc')), ['a', 'b', 'c'])
        self.assertEqual(list(arg_to_iter([1,2,3])), [1,2,3])

if __name__ == "__main__":
    unittest.main()
