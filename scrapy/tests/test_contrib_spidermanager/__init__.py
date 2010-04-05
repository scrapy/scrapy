import unittest

# just a hack to avoid cyclic imports of scrapy.spider when running this test
# alone
import scrapy.spider 
from scrapy.contrib.spidermanager import TwistedPluginSpiderManager
from scrapy.http import Request

class TwistedPluginSpiderManagerTest(unittest.TestCase):

    def setUp(self):
        self.spiderman = TwistedPluginSpiderManager()
        assert not self.spiderman.loaded
        self.spiderman.load(['scrapy.tests.test_contrib_spidermanager'])
        assert self.spiderman.loaded

    def test_list(self):
        self.assertEqual(set(self.spiderman.list()), 
            set(['spider1', 'spider2']))

    def test_create(self):
        spider1 = self.spiderman.create("spider1")
        self.assertEqual(spider1.__class__.__name__, 'Spider1')
        spider2 = self.spiderman.create("spider2", foo="bar")
        self.assertEqual(spider2.__class__.__name__, 'Spider2')
        self.assertEqual(spider2.foo, 'bar')

    def test_find_by_request(self):
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy1.org/test')),
            ['spider1'])
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy2.org/test')),
            ['spider2'])
        self.assertEqual(set(self.spiderman.find_by_request(Request('http://scrapy3.org/test'))),
            set(['spider1', 'spider2']))
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy999.org/test')),
            [])

if __name__ == '__main__':
    unittest.main()
