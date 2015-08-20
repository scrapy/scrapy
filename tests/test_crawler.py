import warnings
import unittest

import mock

import scrapy
from scrapy.addons import Addon, AddonManager
from scrapy.crawler import Crawler, CrawlerRunner, CrawlerProcess
from scrapy.settings import Settings, default_settings
from scrapy.spiderloader import SpiderLoader
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.misc import load_object
from scrapy.extensions.throttle import AutoThrottle


class BaseCrawlerTest(unittest.TestCase):

    def assertOptionIsDefault(self, settings, key):
        self.assertIsInstance(settings, Settings)
        self.assertEqual(settings[key], getattr(default_settings, key))


class CrawlerTestCase(BaseCrawlerTest):

    def setUp(self):
        self.crawler = Crawler(DefaultSpider, Settings())

    def test_deprecated_attribute_spiders(self):
        with warnings.catch_warnings(record=True) as w:
            spiders = self.crawler.spiders
            self.assertEqual(len(w), 1)
            self.assertIn("Crawler.spiders", str(w[0].message))
            sl_cls = load_object(self.crawler.settings['SPIDER_LOADER_CLASS'])
            self.assertIsInstance(spiders, sl_cls)

            self.crawler.spiders
            self.assertEqual(len(w), 1, "Warn deprecated access only once")

    def test_populate_spidercls_settings(self):
        spider_settings = {'TEST1': 'spider', 'TEST2': 'spider'}
        project_settings = {'TEST1': 'project', 'TEST3': 'project'}

        class CustomSettingsSpider(DefaultSpider):
            custom_settings = spider_settings

        settings = Settings()
        settings.setdict(project_settings, priority='project')
        crawler = Crawler(CustomSettingsSpider, settings)

        self.assertEqual(crawler.settings.get('TEST1'), 'spider')
        self.assertEqual(crawler.settings.get('TEST2'), 'spider')
        self.assertEqual(crawler.settings.get('TEST3'), 'project')

        self.assertFalse(settings.frozen)
        self.assertTrue(crawler.settings.frozen)

    def test_configure_addons_from_spidercls_settings(self):
        addoncfg = {'testkey': 'testval'}
        class CustomSettingsSpider(DefaultSpider):
            custom_settings = {
                'INSTALLED_ADDONS': ('tests.test_addons.addons.GoodAddon', ),
                'GOODADDON': addoncfg,
                }
        settings = Settings()
        crawler = Crawler(CustomSettingsSpider, settings)
        self.assertIn('GoodAddon', crawler.addons)
        self.assertEqual(crawler.addons.configs['GoodAddon'], addoncfg)

    def test_spidercls_update_callbacks_called(self):
        class CallbackSpider(DefaultSpider):
            @classmethod
            def update_addons(config, addons): pass
            @classmethod
            def update_settings(config, settings): pass
        with mock.patch.object(CallbackSpider, 'update_addons') as mock_ua, \
                mock.patch.object(CallbackSpider, 'update_settings') as mock_us:
            addonmgr = AddonManager()
            settings = Settings()
            crawler = Crawler(CallbackSpider, settings, addonmgr)
            mock_ua.assert_called_once_with(addonmgr.spiderargs, addonmgr)
            mock_us.assert_called_once_with(addonmgr.spiderargs, settings)

    def test_populate_addons_settings(self):
        class TestAddon(Addon):
            name = 'TestAddon'
            version = '1.0'
        addonconfig = {'TEST1': 'addon', 'TEST2': 'addon', 'TEST3': 'addon'}
        class TestAddon2(Addon):
            name = 'testAddon2'
            version = '1.0'
        addonconfig2 = {'TEST': 'addon2'}

        settings = Settings()
        settings.set('TESTADDON_TEST1', 'project', priority='project')
        settings.set('TESTADDON_TEST2', 'default', priority='default')
        addonmgr = AddonManager()
        addonmgr.add(TestAddon(), addonconfig)
        addonmgr.add(TestAddon2(), addonconfig2)
        crawler = Crawler(DefaultSpider, settings, addonmgr)

        self.assertEqual(crawler.settings['TESTADDON_TEST1'], 'project')
        self.assertEqual(crawler.settings['TESTADDON_TEST2'], 'addon')
        self.assertEqual(crawler.settings['TESTADDON_TEST3'], 'addon')
        self.assertEqual(crawler.settings['TESTADDON2_TEST'], 'addon2')

    def test_addons_set_spider_arguments(self):
        class MyAddon(Addon):
            name = 'MyAddon'
            version = '1.0'
            def update_addons(self, config, addons):
                addons.spiderargs['addonkey'] = 'addonval'
                addons.spiderargs['shared'] = 'addonval'
                addons.spiderargs['defaultkey2'] = 'addonval'

        class ArgumentSpider(DefaultSpider):
            def __init__(self, defaultkey='def', defaultkey2='def2', **kwargs):
                super(ArgumentSpider, self).__init__(defaultkey=defaultkey,
                                                     defaultkey2=defaultkey2,
                                                     **kwargs)

        addonmgr = AddonManager()
        addonmgr.add(MyAddon())
        crawler = Crawler(ArgumentSpider, Settings(), addonmgr)
        spider = crawler._create_spider(cmdlinekey='cmdlineval',
                                        shared='cmdlineval')

        self.assertEqual(spider.defaultkey, 'def')
        self.assertEqual(spider.defaultkey2, 'addonval')
        self.assertEqual(spider.addonkey, 'addonval')
        self.assertEqual(spider.shared, 'cmdlineval')
        self.assertEqual(spider.cmdlinekey, 'cmdlineval')

    def test_crawler_accepts_dict(self):
        crawler = Crawler(DefaultSpider, {'foo': 'bar'})
        self.assertEqual(crawler.settings['foo'], 'bar')
        self.assertOptionIsDefault(crawler.settings, 'RETRY_ENABLED')

    def test_crawler_accepts_None(self):
        crawler = Crawler(DefaultSpider)
        self.assertOptionIsDefault(crawler.settings, 'RETRY_ENABLED')


class SpiderSettingsTestCase(unittest.TestCase):
    def test_spider_custom_settings(self):
        class MySpider(scrapy.Spider):
            name = 'spider'
            custom_settings = {
                'AUTOTHROTTLE_ENABLED': True
            }

        crawler = Crawler(MySpider, {})
        enabled_exts = [e.__class__ for e in crawler.extensions.middlewares]
        self.assertIn(AutoThrottle, enabled_exts)


class SpiderLoaderWithWrongInterface(object):

    def unneeded_method(self):
        pass


class CustomSpiderLoader(SpiderLoader):
    pass


class CrawlerRunnerTestCase(BaseCrawlerTest):

    def test_spider_manager_verify_interface(self):
        settings = Settings({
            'SPIDER_LOADER_CLASS': 'tests.test_crawler.SpiderLoaderWithWrongInterface'
        })
        with warnings.catch_warnings(record=True) as w, \
                self.assertRaises(AttributeError):
            CrawlerRunner(settings)
            self.assertEqual(len(w), 1)
            self.assertIn("SPIDER_LOADER_CLASS", str(w[0].message))
            self.assertIn("scrapy.interfaces.ISpiderLoader", str(w[0].message))

    def test_crawler_runner_accepts_dict(self):
        runner = CrawlerRunner({'foo': 'bar'})
        self.assertEqual(runner.settings['foo'], 'bar')
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')

    def test_crawler_runner_accepts_None(self):
        runner = CrawlerRunner()
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')

    def test_deprecated_attribute_spiders(self):
        with warnings.catch_warnings(record=True) as w:
            runner = CrawlerRunner(Settings())
            spiders = runner.spiders
            self.assertEqual(len(w), 1)
            self.assertIn("CrawlerRunner.spiders", str(w[0].message))
            self.assertIn("CrawlerRunner.spider_loader", str(w[0].message))
            sl_cls = load_object(runner.settings['SPIDER_LOADER_CLASS'])
            self.assertIsInstance(spiders, sl_cls)

    def test_spidermanager_deprecation(self):
        with warnings.catch_warnings(record=True) as w:
            runner = CrawlerRunner({
                'SPIDER_MANAGER_CLASS': 'tests.test_crawler.CustomSpiderLoader'
            })
            self.assertIsInstance(runner.spider_loader, CustomSpiderLoader)
            self.assertEqual(len(w), 1)
            self.assertIn('Please use SPIDER_LOADER_CLASS', str(w[0].message))


class CrawlerProcessTest(BaseCrawlerTest):
    def test_crawler_process_accepts_dict(self):
        runner = CrawlerProcess({'foo': 'bar'})
        self.assertEqual(runner.settings['foo'], 'bar')
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')

    def test_crawler_process_accepts_None(self):
        runner = CrawlerProcess()
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')
