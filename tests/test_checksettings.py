from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import get_crawler
from scrapy.extensions.checksettings import CheckSettings
from tests.spiders import ItemSpider
from tests.mockserver import MockServer


class TestCheckSettings(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_checksettings_not_used_settings(self):
        settings = {
            'CHECK_SETTINGS_ENABLED': True,
            "NOT_USED_SETTING": True,
            "COOKIES_ENAVLED": False,
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(mockserver=self.mockserver)
        check_settings = CheckSettings(crawler)
        check_settings.spider_closed()
        self.assertEqual(
            check_settings.not_used_settings, ["NOT_USED_SETTING", "COOKIES_ENAVLED"])

    @defer.inlineCallbacks
    def test_checksettings_suggestions(self):
        settings = {
            "CHECK_SETTINGS_ENABLED": True,
            "DOWNLOADER_STATSIE": True,
            "COOKIES_ENABLEDIE": True,
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(mockserver=self.mockserver)
        check_settings = CheckSettings(crawler)
        check_settings.spider_closed()
        self.assertEqual(check_settings.get_suggestions(), {
            "DOWNLOADER_STATSIE": "DOWNLOADER_STATS",
            "COOKIES_ENABLEDIE": "COOKIES_ENABLED",
        })
        self.assertEqual(check_settings.not_used_settings,
                         ["DOWNLOADER_STATSIE", "COOKIES_ENABLEDIE"])