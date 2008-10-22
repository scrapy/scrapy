from twisted.trial import unittest

class SpidermonkeyTest(unittest.TestCase):

    def setUp(self):
        try:
            from spidermonkey import Runtime
            r = Runtime()
            self.cx = r.new_context()
        except ImportError:
            raise unittest.SkipTest("Spidermonkey C library not available")

    def test_spidermonkey(self):
        """Spidermonkey basic functionality tests"""

        self.cx.eval_script("var item0={'price':50}")
        self.cx.eval_script("var item1={'price':20}")
        self.assertEqual(self.cx.eval_script("item0"), {'price': 50})
        self.assertEqual(self.cx.eval_script("item1"), {'price': 20})
        self.cx.eval_script("var itemArray=new Array(item0, item1)")
        self.assertEqual(self.cx.eval_script("itemArray"), [{'price': 50}, {'price':20}])

if __name__ == "__main__":
    unittest.main()
