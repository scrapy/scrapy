import unittest
from cStringIO import StringIO

from scrapy.utils.misc import load_object, arg_to_iter
from scrapy.item import ScrapedItem

class UtilsMiscTestCase(unittest.TestCase):

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
