import sys
import os
import shutil
import warnings

from zope.interface.verify import verifyObject
from twisted.trial import unittest


# ugly hack to avoid cyclic imports of scrapy.spiders when running this test
# alone
import scrapy
import tempfile
from scrapy.interfaces import ISpiderLoader
from scrapy.spiderloader import SpiderLoader
from scrapy.settings import Settings
from scrapy.http import Request
from scrapy.crawler import CrawlerRunner

module_dir = os.path.dirname(os.path.abspath(__file__))


def _copytree(source, target):
    try:
        shutil.copytree(source, target)
    except shutil.Error:
        pass


class SpiderLoaderTest(unittest.TestCase):

    def setUp(self):
        orig_spiders_dir = os.path.join(module_dir, 'test_spiders')
        self.tmpdir = tempfile.mkdtemp()
        self.spiders_dir = os.path.join(self.tmpdir, 'test_spiders_xxx')
        _copytree(orig_spiders_dir, self.spiders_dir)
        sys.path.append(self.tmpdir)
        settings = Settings({'SPIDER_MODULES': ['test_spiders_xxx']})
        self.spider_loader = SpiderLoader.from_settings(settings)

    def tearDown(self):
        del self.spider_loader
        del sys.modules['test_spiders_xxx']
        sys.path.remove(self.tmpdir)

    def test_interface(self):
        verifyObject(ISpiderLoader, self.spider_loader)

    def test_list(self):
        self.assertEqual(
            set(self.spider_loader.list()),
            {'spider1', 'spider2', 'spider3', 'spider4'})

    def test_load(self):
        spider1 = self.spider_loader.load("spider1")
        self.assertEqual(spider1.__name__, 'Spider1')

    def test_find_by_request(self):
        self.assertEqual(
            self.spider_loader.find_by_request(Request('http://scrapy1.org/test')),
            ['spider1'])
        self.assertEqual(
            self.spider_loader.find_by_request(Request('http://scrapy2.org/test')),
            ['spider2'])
        self.assertEqual(
            set(self.spider_loader.find_by_request(Request('http://scrapy3.org/test'))),
            {'spider1', 'spider2'})
        self.assertEqual(
            self.spider_loader.find_by_request(Request('http://scrapy999.org/test')),
            [])
        self.assertEqual(
            self.spider_loader.find_by_request(Request('http://spider3.com')),
            [])
        self.assertEqual(
            self.spider_loader.find_by_request(Request('http://spider3.com/onlythis')),
            ['spider3'])

    def test_load_spider_module(self):
        module = 'tests.test_spiderloader.test_spiders.spider1'
        settings = Settings({'SPIDER_MODULES': [module]})
        self.spider_loader = SpiderLoader.from_settings(settings)
        assert len(self.spider_loader._spiders) == 1

    def test_load_spider_module_multiple(self):
        prefix = 'tests.test_spiderloader.test_spiders.'
        module = ','.join(prefix + s for s in ('spider1', 'spider2'))
        settings = Settings({'SPIDER_MODULES': module})
        self.spider_loader = SpiderLoader.from_settings(settings)
        assert len(self.spider_loader._spiders) == 2

    def test_load_base_spider(self):
        module = 'tests.test_spiderloader.test_spiders.spider0'
        settings = Settings({'SPIDER_MODULES': [module]})
        self.spider_loader = SpiderLoader.from_settings(settings)
        assert len(self.spider_loader._spiders) == 0

    def test_crawler_runner_loading(self):
        module = 'tests.test_spiderloader.test_spiders.spider1'
        runner = CrawlerRunner({'SPIDER_MODULES': [module]})

        self.assertRaisesRegex(KeyError, 'Spider not found',
                               runner.create_crawler, 'spider2')

        crawler = runner.create_crawler('spider1')
        self.assertTrue(issubclass(crawler.spidercls, scrapy.Spider))
        self.assertEqual(crawler.spidercls.name, 'spider1')

    def test_bad_spider_modules_exception(self):

        module = 'tests.test_spiderloader.test_spiders.doesnotexist'
        settings = Settings({'SPIDER_MODULES': [module]})
        self.assertRaises(ImportError, SpiderLoader.from_settings, settings)

    def test_bad_spider_modules_warning(self):

        with warnings.catch_warnings(record=True) as w:
            module = 'tests.test_spiderloader.test_spiders.doesnotexist'
            settings = Settings({'SPIDER_MODULES': [module],
                                 'SPIDER_LOADER_WARN_ONLY': True})
            spider_loader = SpiderLoader.from_settings(settings)
            if str(w[0].message).startswith("_SixMetaPathImporter"):
                # needed on 3.10 because of https://github.com/benjaminp/six/issues/349,
                # at least until all six versions we can import (including botocore.vendored.six)
                # are updated to 1.16.0+
                w.pop(0)
            self.assertIn("Could not load spiders from module", str(w[0].message))

            spiders = spider_loader.list()
            self.assertEqual(spiders, [])


class DuplicateSpiderNameLoaderTest(unittest.TestCase):

    def setUp(self):
        orig_spiders_dir = os.path.join(module_dir, 'test_spiders')
        self.tmpdir = self.mktemp()
        os.mkdir(self.tmpdir)
        self.spiders_dir = os.path.join(self.tmpdir, 'test_spiders_xxx')
        _copytree(orig_spiders_dir, self.spiders_dir)
        sys.path.append(self.tmpdir)
        self.settings = Settings({'SPIDER_MODULES': ['test_spiders_xxx']})

    def tearDown(self):
        del sys.modules['test_spiders_xxx']
        sys.path.remove(self.tmpdir)

    def test_dupename_warning(self):
        # copy 1 spider module so as to have duplicate spider name
        shutil.copyfile(os.path.join(self.tmpdir, 'test_spiders_xxx', 'spider3.py'),
                        os.path.join(self.tmpdir, 'test_spiders_xxx', 'spider3dupe.py'))

        with warnings.catch_warnings(record=True) as w:
            spider_loader = SpiderLoader.from_settings(self.settings)

            self.assertEqual(len(w), 1)
            msg = str(w[0].message)
            self.assertIn("several spiders with the same name", msg)
            self.assertIn("'spider3'", msg)
            self.assertTrue(msg.count("'spider3'") == 2)

            self.assertNotIn("'spider1'", msg)
            self.assertNotIn("'spider2'", msg)
            self.assertNotIn("'spider4'", msg)

            spiders = set(spider_loader.list())
            self.assertEqual(spiders, {'spider1', 'spider2', 'spider3', 'spider4'})

    def test_multiple_dupename_warning(self):
        # copy 2 spider modules so as to have duplicate spider name
        # This should issue 2 warning, 1 for each duplicate spider name
        shutil.copyfile(os.path.join(self.tmpdir, 'test_spiders_xxx', 'spider1.py'),
                        os.path.join(self.tmpdir, 'test_spiders_xxx', 'spider1dupe.py'))
        shutil.copyfile(os.path.join(self.tmpdir, 'test_spiders_xxx', 'spider2.py'),
                        os.path.join(self.tmpdir, 'test_spiders_xxx', 'spider2dupe.py'))

        with warnings.catch_warnings(record=True) as w:
            spider_loader = SpiderLoader.from_settings(self.settings)

            self.assertEqual(len(w), 1)
            msg = str(w[0].message)
            self.assertIn("several spiders with the same name", msg)
            self.assertIn("'spider1'", msg)
            self.assertTrue(msg.count("'spider1'") == 2)

            self.assertIn("'spider2'", msg)
            self.assertTrue(msg.count("'spider2'") == 2)

            self.assertNotIn("'spider3'", msg)
            self.assertNotIn("'spider4'", msg)

            spiders = set(spider_loader.list())
            self.assertEqual(spiders, {'spider1', 'spider2', 'spider3', 'spider4'})
