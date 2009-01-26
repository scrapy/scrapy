import unittest
from scrapy.core.scheduler import GroupFilter

class GroupFilterTest(unittest.TestCase):

    def test_groupfilter(self):
        k1 = "id1"
        k2 = "id1"

        f = GroupFilter()
        f.open("mygroup")
        self.assertTrue(f.add("mygroup", k1))
        self.assertFalse(f.add("mygroup", k1))
        self.assertFalse(f.add("mygroup", k2))

        f.open('anothergroup')
        self.assertTrue(f.add("anothergroup", k1))
        self.assertFalse(f.add("anothergroup", k1))
        self.assertFalse(f.add("anothergroup", k2))

        f.close('mygroup')
        f.open('mygroup')
        self.assertTrue(f.add("mygroup", k2))
        self.assertFalse(f.add("mygroup", k1))

if __name__ == "__main__":
    unittest.main()
