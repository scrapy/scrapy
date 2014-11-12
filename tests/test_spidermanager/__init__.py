import sys
import os
import shutil

from zope.interface.verify import verifyObject
from twisted.trial import unittest


# ugly hack to avoid cyclic imports of scrapy.spider when running this test
# alone
from scrapy.interfaces import ISpiderManager
from scrapy.spidermanager import SpiderManager
from scrapy.settings import Settings
from scrapy.http import Request

module_dir = os.path.dirname(os.path.abspath(__file__))

class SpiderManagerTest(unittest.TestCase):

    def setUp(self):
        orig_spiders_dir = os.path.join(module_dir, 'test_spiders')
        self.tmpdir = self.mktemp()
        os.mkdir(self.tmpdir)
        self.spiders_dir = os.path.join(self.tmpdir, 'test_spiders_xxx')
        shutil.copytree(orig_spiders_dir, self.spiders_dir)
        sys.path.append(self.tmpdir)
        settings = Settings({'SPIDER_MODULES': ['test_spiders_xxx']})
        self.spiderman = SpiderManager.from_settings(settings)

    def tearDown(self):
        del self.spiderman
        del sys.modules['test_spiders_xxx']
        sys.path.remove(self.tmpdir)

    def test_interface(self):
        verifyObject(ISpiderManager, self.spiderman)

    def test_list(self):
        self.assertEqual(set(self.spiderman.list()),
            set(['spider1', 'spider2', 'spider3']))

    def test_load(self):
        spider1 = self.spiderman.load("spider1")
        self.assertEqual(spider1.__name__, 'Spider1')

    def test_find_by_request(self):
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy1.org/test')),
            ['spider1'])
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy2.org/test')),
            ['spider2'])
        self.assertEqual(set(self.spiderman.find_by_request(Request('http://scrapy3.org/test'))),
            set(['spider1', 'spider2']))
        self.assertEqual(self.spiderman.find_by_request(Request('http://scrapy999.org/test')),
            [])
        self.assertEqual(self.spiderman.find_by_request(Request('http://spider3.com')),
            [])
        self.assertEqual(self.spiderman.find_by_request(Request('http://spider3.com/onlythis')),
            ['spider3'])

    def test_load_spider_module(self):
        module = 'tests.test_spidermanager.test_spiders.spider1'
        settings = Settings({'SPIDER_MODULES': [module]})
        self.spiderman = SpiderManager.from_settings(settings)
        assert len(self.spiderman._spiders) == 1

    def test_load_spider_module(self):
        prefix = 'tests.test_spidermanager.test_spiders.'
        module = ','.join(prefix + s for s in ('spider1', 'spider2'))
        settings = Settings({'SPIDER_MODULES': module})
        self.spiderman = SpiderManager.from_settings(settings)
        assert len(self.spiderman._spiders) == 2

    def test_load_base_spider(self):
        module = 'tests.test_spidermanager.test_spiders.spider0'
        settings = Settings({'SPIDER_MODULES': [module]})
        self.spiderman = SpiderManager.from_settings(settings)
        assert len(self.spiderman._spiders) == 0
