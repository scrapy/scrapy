import logging
import os
import subprocess
import sys
import warnings

from pytest import raises, mark
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial import unittest

import scrapy
from scrapy.crawler import Crawler, CrawlerRunner, CrawlerProcess
from scrapy.settings import Settings, default_settings
from scrapy.spiderloader import SpiderLoader
from scrapy.utils.log import configure_logging, get_scrapy_root_handler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.misc import load_object
from scrapy.extensions.throttle import AutoThrottle
from scrapy.extensions import telnet
from scrapy.utils.test import get_testenv


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
            is_one_warning = len(w) == 1
            if not is_one_warning:
                for warning in w:
                    print(warning)
            self.assertTrue(is_one_warning, "Warn deprecated access only once")

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

    def test_crawler_accepts_dict(self):
        crawler = Crawler(DefaultSpider, {'foo': 'bar'})
        self.assertEqual(crawler.settings['foo'], 'bar')
        self.assertOptionIsDefault(crawler.settings, 'RETRY_ENABLED')

    def test_crawler_accepts_None(self):
        crawler = Crawler(DefaultSpider)
        self.assertOptionIsDefault(crawler.settings, 'RETRY_ENABLED')

    def test_crawler_rejects_spider_objects(self):
        with raises(ValueError):
            Crawler(DefaultSpider())


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


class CrawlerLoggingTestCase(unittest.TestCase):
    def test_no_root_handler_installed(self):
        handler = get_scrapy_root_handler()
        if handler is not None:
            logging.root.removeHandler(handler)

        class MySpider(scrapy.Spider):
            name = 'spider'

        crawler = Crawler(MySpider, {})
        assert get_scrapy_root_handler() is None

    def test_spider_custom_settings_log_level(self):
        log_file = self.mktemp()
        class MySpider(scrapy.Spider):
            name = 'spider'
            custom_settings = {
                'LOG_LEVEL': 'INFO',
                'LOG_FILE': log_file,
                # disable telnet if not available to avoid an extra warning
                'TELNETCONSOLE_ENABLED': telnet.TWISTED_CONCH_AVAILABLE,
            }

        configure_logging()
        self.assertEqual(get_scrapy_root_handler().level, logging.DEBUG)
        crawler = Crawler(MySpider, {})
        self.assertEqual(get_scrapy_root_handler().level, logging.INFO)
        info_count = crawler.stats.get_value('log_count/INFO')
        logging.debug('debug message')
        logging.info('info message')
        logging.warning('warning message')
        logging.error('error message')

        with open(log_file, 'rb') as fo:
            logged = fo.read().decode('utf8')

        self.assertNotIn('debug message', logged)
        self.assertIn('info message', logged)
        self.assertIn('warning message', logged)
        self.assertIn('error message', logged)
        self.assertEqual(crawler.stats.get_value('log_count/ERROR'), 1)
        self.assertEqual(crawler.stats.get_value('log_count/WARNING'), 1)
        self.assertEqual(
            crawler.stats.get_value('log_count/INFO') - info_count, 1)
        self.assertEqual(crawler.stats.get_value('log_count/DEBUG', 0), 0)


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
        with warnings.catch_warnings(record=True) as w:
            self.assertRaises(AttributeError, CrawlerRunner, settings)
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


class CrawlerProcessTest(BaseCrawlerTest):
    def test_crawler_process_accepts_dict(self):
        runner = CrawlerProcess({'foo': 'bar'})
        self.assertEqual(runner.settings['foo'], 'bar')
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')

    def test_crawler_process_accepts_None(self):
        runner = CrawlerProcess()
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')


class ExceptionSpider(scrapy.Spider):
    name = 'exception'

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        raise ValueError('Exception in from_crawler method')


class NoRequestsSpider(scrapy.Spider):
    name = 'no_request'

    def start_requests(self):
        return []


@mark.usefixtures('reactor_pytest')
class CrawlerRunnerHasSpider(unittest.TestCase):

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_successful(self):
        runner = CrawlerRunner()
        yield runner.crawl(NoRequestsSpider)
        self.assertEqual(runner.bootstrap_failed, False)

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_successful_for_several(self):
        runner = CrawlerRunner()
        yield runner.crawl(NoRequestsSpider)
        yield runner.crawl(NoRequestsSpider)
        self.assertEqual(runner.bootstrap_failed, False)

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_failed(self):
        runner = CrawlerRunner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            self.fail('Exception should be raised from spider')

        self.assertEqual(runner.bootstrap_failed, True)

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_failed_for_several(self):
        runner = CrawlerRunner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            self.fail('Exception should be raised from spider')

        yield runner.crawl(NoRequestsSpider)

        self.assertEqual(runner.bootstrap_failed, True)

    def test_crawler_runner_asyncio_enabled_true(self):
        if self.reactor_pytest == 'asyncio':
            runner = CrawlerRunner(settings={'ASYNCIO_REACTOR': True})
        else:
            msg = "ASYNCIO_REACTOR is on but the Twisted asyncio reactor is not installed"
            with self.assertRaisesRegex(Exception, msg):
                runner = CrawlerRunner(settings={'ASYNCIO_REACTOR': True})

    @defer.inlineCallbacks
    def test_crawler_process_asyncio_enabled_true(self):
        with LogCapture(level=logging.DEBUG) as log:
            if self.reactor_pytest == 'asyncio':
                runner = CrawlerProcess(settings={'ASYNCIO_REACTOR': True})
                yield runner.crawl(NoRequestsSpider)
                self.assertIn("Asyncio reactor is installed", str(log))
            else:
                msg = "ASYNCIO_REACTOR is on but the Twisted asyncio reactor is not installed"
                with self.assertRaisesRegex(Exception, msg):
                    runner = CrawlerProcess(settings={'ASYNCIO_REACTOR': True})

    @defer.inlineCallbacks
    def test_crawler_process_asyncio_enabled_false(self):
        runner = CrawlerProcess(settings={'ASYNCIO_REACTOR': False})
        with LogCapture(level=logging.DEBUG) as log:
            yield runner.crawl(NoRequestsSpider)
            self.assertNotIn("Asyncio reactor is installed", str(log))


class CrawlerProcessSubprocess(unittest.TestCase):
    script_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'CrawlerProcess')

    def run_script(self, script_name):
        script_path = os.path.join(self.script_dir, script_name)
        args = (sys.executable, script_path)
        p = subprocess.Popen(args, env=get_testenv(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        return stderr.decode('utf-8')

    def test_simple(self):
        log = self.run_script('simple.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertNotIn("DEBUG: Asyncio reactor is installed", log)

    def test_asyncio_enabled_no_reactor(self):
        log = self.run_script('asyncio_enabled_no_reactor.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertIn("DEBUG: Asyncio reactor is installed", log)

    def test_asyncio_enabled_reactor(self):
        log = self.run_script('asyncio_enabled_reactor.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertIn("DEBUG: Asyncio reactor is installed", log)
