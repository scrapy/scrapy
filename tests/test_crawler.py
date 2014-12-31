import warnings
import unittest

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.crawler import Crawler, CrawlerRunner
from scrapy.settings import Settings
from scrapy.utils.engine import get_engine_status
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler

from tests.mockserver import MockServer
from tests.spiders import SingleRequestSpider


class CrawlerTestCase(unittest.TestCase):

    def setUp(self):
        self.crawler = Crawler(DefaultSpider, Settings())

    def test_deprecated_attribute_spiders(self):
        with warnings.catch_warnings(record=True) as w:
            spiders = self.crawler.spiders
            self.assertEqual(len(w), 1)
            self.assertIn("Crawler.spiders", str(w[0].message))
            sm_cls = load_object(self.crawler.settings['SPIDER_MANAGER_CLASS'])
            self.assertIsInstance(spiders, sm_cls)

            self.crawler.spiders
            self.assertEqual(len(w), 1, "Warn deprecated access only once")


class CrawlerStartRequestsTestCase(TestCase):

    def setUp(self):
        self.crawler = get_crawler(SingleRequestSpider)
        self.engine_status = []
        self.url = "http://localhost:8998/"
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    def _cb(self, response):
        self.engine_status.append(get_engine_status(self.crawler.engine))

    def _assert_engine_worked(self):
        stats = self.crawler.stats.get_stats()
        self.assertIn('start_time', stats)
        self.assertIn('finish_time', stats)
        self.assertEquals(stats['finish_reason'], 'finished')

    @defer.inlineCallbacks
    def test_start_requests_enabled(self):
        yield self.crawler.crawl(seed=self.url, callback_func=self._cb)
        self._assert_engine_worked()
        self.assertEqual(len(self.engine_status), 1, self.engine_status)
        est = dict(self.engine_status[0])
        self.assertEqual(est['engine.spider.name'],
                         self.crawler.spider.name)
        self.assertEqual(est['len(engine.scraper.slot.active)'], 1)
        stats = self.crawler.stats.get_stats()
        self.assertEqual(stats['scheduler/enqueued'], 1)
        self.assertEqual(stats['scheduler/dequeued'], 1)
        self.assertEqual(stats['downloader/request_count'], 1)
        self.assertEqual(stats['downloader/response_count'], 1)

    @defer.inlineCallbacks
    def test_start_requests_disabled(self):
        self.crawler.start_requests = False
        yield self.crawler.crawl(seed=self.url, callback_func=self._cb)
        self._assert_engine_worked()
        self.assertEqual(len(self.engine_status), 0, self.engine_status)
        stats = self.crawler.stats.get_stats()
        self.assertNotIn('scheduler/enqueued', stats)
        self.assertNotIn('scheduler/dequeued', stats)
        self.assertNotIn('downloader/request_count', stats)
        self.assertNotIn('downloader/response_count', stats)


class CrawlerRunnerTest(unittest.TestCase):

    def setUp(self):
        self.crawler_runner = CrawlerRunner(Settings())

    def tearDown(self):
        return self.crawler_runner.stop()

    @defer.inlineCallbacks
    def test_populate_spidercls_settings(self):
        spider_settings = {'TEST1': 'spider', 'TEST2': 'spider'}
        project_settings = {'TEST1': 'project', 'TEST3': 'project'}

        class CustomSettingsSpider(DefaultSpider):
            custom_settings = spider_settings

        self.crawler_runner.settings.setdict(project_settings,
                                             priority='project')

        d = self.crawler_runner.crawl(CustomSettingsSpider)
        crawler = list(self.crawler_runner.crawlers)[0]
        yield d
        self.assertEqual(crawler.settings.get('TEST1'), 'spider')
        self.assertEqual(crawler.settings.get('TEST2'), 'spider')
        self.assertEqual(crawler.settings.get('TEST3'), 'project')
