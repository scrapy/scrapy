from testfixtures import LogCapture
from tests.mockserver import MockServer
from tests.spiders import ItemSpider
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.utils.test import get_crawler
from scrapy.extensions.checksettings import CheckSettings


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
        check_settings.spider_opened()
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
        check_settings.spider_opened()
        self.assertEqual(check_settings.get_suggestions(), {
            "DOWNLOADER_STATSIE": "DOWNLOADER_STATS",
            "COOKIES_ENABLEDIE": "COOKIES_ENABLED",
        })
        self.assertEqual(check_settings.not_used_settings,
                         ["DOWNLOADER_STATSIE", "COOKIES_ENABLEDIE"])

    @defer.inlineCallbacks
    def test_checksettings_not_used_message(self):
        settings = {
            "CHECK_SETTINGS_ENABLED": True,
            "NOT_USED_SETTING_FOO": True,
            "NOT_USED_SETTING_BAR": True,
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(mockserver=self.mockserver)
        check_settings = CheckSettings(crawler)
        with LogCapture() as lc:
            check_settings.spider_opened()
            lc.check(
                ("scrapy.extensions.checksettings", "WARNING",
                 "Not used settings: \n['NOT_USED_SETTING_FOO', 'NOT_USED_SETTING_BAR']")
            )

    @defer.inlineCallbacks
    def test_checksettings_suggestion_message(self):
        settings = {
            "CHECK_SETTINGS_ENABLED": True,
            "COOKIES_ENABLEDIE": True,
            "DOWNLOADER_STATSIE": True,
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(mockserver=self.mockserver)
        check_settings = CheckSettings(crawler)
        with LogCapture() as lc:
            check_settings.spider_opened()
            lc.check(
                ("scrapy.extensions.checksettings", "WARNING",
                 "Not used settings: \n['COOKIES_ENABLEDIE', 'DOWNLOADER_STATSIE']"),
                ("scrapy.extensions.checksettings", "INFO",
                 "Settings suggestions: \n"
                 "['COOKIES_ENABLEDIE, did you mean COOKIES_ENABLED ?',\n"
                 " 'DOWNLOADER_STATSIE, did you mean DOWNLOADER_STATS ?']")
            )

    @defer.inlineCallbacks
    def test_checksettings_ignored_list(self):
        settings = {
            "CHECK_SETTINGS_ENABLED": True,
            "COOKIES_ENABLEDIE": True,
            "DOWNLOADER_STATSIE": True,
            "CHECK_SETTINGS_IGNORED": ["DOWNLOADER_STATSIE", "COOKIES_ENABLEDIE"]
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(mockserver=self.mockserver)
        check_settings = CheckSettings(crawler)
        with LogCapture() as lc:
            check_settings.spider_opened()
            lc.check()
