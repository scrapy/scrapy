import unittest

from scrapy.link import Link

class LinkTest(unittest.TestCase):

    def test_eq_and_hash(self):
        l1 = Link("http://www.example.com")
        l2 = Link("http://www.example.com/other")
        l3 = Link("http://www.example.com")

        self.assertEqual(l1, l1)
        self.assertEqual(hash(l1), hash(l1))
        self.assertNotEqual(l1, l2)
        self.assertNotEqual(hash(l1), hash(l2))
        self.assertEqual(l1, l3)
        self.assertEqual(hash(l1), hash(l3))

        l4 = Link("http://www.example.com", text="test")
        l5 = Link("http://www.example.com", text="test2")
        l6 = Link("http://www.example.com", text="test")

        self.assertEqual(l4, l4)
        self.assertEqual(hash(l4), hash(l4))
        self.assertNotEqual(l4, l5)
        self.assertNotEqual(hash(l4), hash(l5))
        self.assertEqual(l4, l6)
        self.assertEqual(hash(l4), hash(l6))
