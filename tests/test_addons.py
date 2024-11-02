import itertools
from typing import Any
from unittest.mock import patch

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from scrapy import Spider
from scrapy.crawler import Crawler, CrawlerRunner
from scrapy.exceptions import NotConfigured
from scrapy.settings import BaseSettings, Settings
from scrapy.utils.test import get_crawler


class SimpleAddon:
    def update_settings(self, settings):
        pass


def get_addon_cls(config: dict[str, Any]) -> type:
    class AddonWithConfig:
        def update_settings(self, settings: BaseSettings):
            settings.update(config, priority="addon")

    return AddonWithConfig


class CreateInstanceAddon:
    def __init__(self, crawler: Crawler) -> None:
        super().__init__()
        self.crawler = crawler
        self.config = crawler.settings.getdict("MYADDON")

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        return cls(crawler)

    def update_settings(self, settings):
        settings.update(self.config, "addon")


class AddonTest(unittest.TestCase):
    def test_update_settings(self):
        settings = BaseSettings()
        settings.set("KEY1", "default", priority="default")
        settings.set("KEY2", "project", priority="project")
        addon_config = {"KEY1": "addon", "KEY2": "addon", "KEY3": "addon"}
        testaddon = get_addon_cls(addon_config)()
        testaddon.update_settings(settings)
        self.assertEqual(settings["KEY1"], "addon")
        self.assertEqual(settings["KEY2"], "project")
        self.assertEqual(settings["KEY3"], "addon")


class AddonManagerTest(unittest.TestCase):
    def test_load_settings(self):
        settings_dict = {
            "ADDONS": {"tests.test_addons.SimpleAddon": 0},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        manager = crawler.addons
        self.assertIsInstance(manager.addons[0], SimpleAddon)

    def test_notconfigured(self):
        class NotConfiguredAddon:
            def update_settings(self, settings):
                raise NotConfigured()

        settings_dict = {
            "ADDONS": {NotConfiguredAddon: 0},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        manager = crawler.addons
        self.assertFalse(manager.addons)

    def test_load_settings_order(self):
        # Get three addons with different settings
        addonlist = []
        for i in range(3):
            addon = get_addon_cls({"KEY1": i})
            addon.number = i
            addonlist.append(addon)
        # Test for every possible ordering
        for ordered_addons in itertools.permutations(addonlist):
            expected_order = [a.number for a in ordered_addons]
            settings = {"ADDONS": {a: i for i, a in enumerate(ordered_addons)}}
            crawler = get_crawler(settings_dict=settings)
            manager = crawler.addons
            self.assertEqual([a.number for a in manager.addons], expected_order)
            self.assertEqual(crawler.settings.getint("KEY1"), expected_order[-1])

    def test_build_from_crawler(self):
        settings_dict = {
            "ADDONS": {"tests.test_addons.CreateInstanceAddon": 0},
            "MYADDON": {"MYADDON_KEY": "val"},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        manager = crawler.addons
        self.assertIsInstance(manager.addons[0], CreateInstanceAddon)
        self.assertEqual(crawler.settings.get("MYADDON_KEY"), "val")

    def test_settings_priority(self):
        config = {
            "KEY": 15,  # priority=addon
        }
        settings_dict = {
            "ADDONS": {get_addon_cls(config): 1},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        self.assertEqual(crawler.settings.getint("KEY"), 15)

        settings = Settings(settings_dict)
        settings.set("KEY", 0, priority="default")
        runner = CrawlerRunner(settings)
        crawler = runner.create_crawler(Spider)
        crawler._apply_settings()
        self.assertEqual(crawler.settings.getint("KEY"), 15)

        settings_dict = {
            "KEY": 20,  # priority=project
            "ADDONS": {get_addon_cls(config): 1},
        }
        settings = Settings(settings_dict)
        settings.set("KEY", 0, priority="default")
        runner = CrawlerRunner(settings)
        crawler = runner.create_crawler(Spider)
        self.assertEqual(crawler.settings.getint("KEY"), 20)

    def test_fallback_workflow(self):
        FALLBACK_SETTING = "MY_FALLBACK_DOWNLOAD_HANDLER"

        class AddonWithFallback:
            def update_settings(self, settings):
                if not settings.get(FALLBACK_SETTING):
                    settings.set(
                        FALLBACK_SETTING,
                        settings.getwithbase("DOWNLOAD_HANDLERS")["https"],
                        "addon",
                    )
                settings["DOWNLOAD_HANDLERS"]["https"] = "AddonHandler"

        settings_dict = {
            "ADDONS": {AddonWithFallback: 1},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        self.assertEqual(
            crawler.settings.getwithbase("DOWNLOAD_HANDLERS")["https"], "AddonHandler"
        )
        self.assertEqual(
            crawler.settings.get(FALLBACK_SETTING),
            "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
        )

        settings_dict = {
            "ADDONS": {AddonWithFallback: 1},
            "DOWNLOAD_HANDLERS": {"https": "UserHandler"},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        self.assertEqual(
            crawler.settings.getwithbase("DOWNLOAD_HANDLERS")["https"], "AddonHandler"
        )
        self.assertEqual(crawler.settings.get(FALLBACK_SETTING), "UserHandler")

    def test_logging_message(self):
        class LoggedAddon:
            def update_settings(self, settings):
                pass

        with patch("scrapy.addons.logger") as logger_mock:
            with patch("scrapy.addons.build_from_crawler") as build_from_crawler_mock:
                settings_dict = {
                    "ADDONS": {LoggedAddon: 1},
                }
                addon = LoggedAddon()
                build_from_crawler_mock.return_value = addon
                crawler = get_crawler(settings_dict=settings_dict)
                logger_mock.info.assert_called_once_with(
                    "Enabled addons:\n%(addons)s",
                    {"addons": [addon]},
                    extra={"crawler": crawler},
                )

    @inlineCallbacks
    def test_enable_addon_in_spider(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler, *args, **kwargs):
                spider = super().from_crawler(crawler, *args, **kwargs)
                addon_config = {"KEY": "addon"}
                addon_cls = get_addon_cls(addon_config)
                spider.settings.set("ADDONS", {addon_cls: 1}, priority="spider")
                return spider

        settings = Settings()
        settings.set("KEY", "default", priority="default")
        runner = CrawlerRunner(settings)
        crawler = runner.create_crawler(MySpider)
        self.assertEqual(crawler.settings.get("KEY"), "default")
        yield crawler.crawl()
        self.assertEqual(crawler.settings.get("KEY"), "addon")
