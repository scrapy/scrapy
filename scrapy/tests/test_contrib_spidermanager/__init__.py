import sys
import os
import weakref
import shutil

from twisted.trial import unittest

# ugly hack to avoid cyclic imports of scrapy.spider when running this test
# alone
import scrapy.spider 
from scrapy.contrib.spidermanager import TwistedPluginSpiderManager
from scrapy.http import Request

module_dir = os.path.dirname(os.path.abspath(__file__))

class TwistedPluginSpiderManagerTest(unittest.TestCase):

    def setUp(self):
        orig_spiders_dir = os.path.join(module_dir, 'test_spiders')
        self.tmpdir = self.mktemp()
        os.mkdir(self.tmpdir)
        self.spiders_dir = os.path.join(self.tmpdir, 'test_spiders_xxx')
        shutil.copytree(orig_spiders_dir, self.spiders_dir)
        sys.path.append(self.tmpdir)
        self.spiderman = TwistedPluginSpiderManager()
        assert not self.spiderman.loaded
        self.spiderman.load(['test_spiders_xxx'])
        assert self.spiderman.loaded

    def tearDown(self):
        del self.spiderman
        sys.path.remove(self.tmpdir)

    def test_list(self):
        self.assertEqual(set(self.spiderman.list()), 
            set(['spider1', 'spider2']))

    def test_create(self):
        spider1 = self.spiderman.create("spider1")
        self.assertEqual(spider1.__class__.__name__, 'Spider1')
        spider2 = self.spiderman.create("spider2", foo="bar")
        self.assertEqual(spider2.__class__.__name__, 'Spider2')
        self.assertEqual(spider2.foo, 'bar')

    def test_create_uses_cache(self):
        # TwistedPluginSpiderManager uses an internal cache which is
        # invalidated in close_spider() but this isn't necessarily the best
        # thing to do in all cases.
        spider1 = self.spiderman.create("spider1")
        spider2 = self.spiderman.create("spider1")
        assert spider1 is spider2

    def test_find_by_request(self):
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy1.org/test')),
            ['spider1'])
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy2.org/test')),
            ['spider2'])
        self.assertEqual(set(self.spiderman.find_by_request(Request('http://scrapy3.org/test'))),
            set(['spider1', 'spider2']))
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy999.org/test')),
            [])

    def test_close_spider_remove_refs(self):
        spider = self.spiderman.create("spider1")
        wref = weakref.ref(spider)
        assert wref()
        self.spiderman.close_spider(spider)
        del spider
        assert not wref()

    def test_close_spider_invalidates_cache(self):
        spider1 = self.spiderman.create("spider1")
        self.spiderman.close_spider(spider1)
        spider2 = self.spiderman.create("spider1")
        assert spider1 is not spider2
