import unittest
from typing import Any, Dict, Optional

from scrapy.crawler import Crawler
from scrapy.settings import BaseSettings
from scrapy.utils.test import get_crawler


class GoodAddon:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.config = config or {}

    def update_settings(self, settings):
        settings.update(self.config, "addon")


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
        testaddon = GoodAddon(addon_config)
        testaddon.update_settings(settings)
        self.assertEqual(settings["KEY1"], "addon")
        self.assertEqual(settings["KEY2"], "project")
        self.assertEqual(settings["KEY3"], "addon")


class AddonManagerTest(unittest.TestCase):
    def test_add(self):
        crawler = get_crawler()
        manager = crawler.addons
        manager.add("tests.test_addons.GoodAddon")
        self.assertIsInstance(manager.addons[0], GoodAddon)

    def test_load_settings(self):
        settings_dict = {
            "ADDONS": {"tests.test_addons.GoodAddon": 0},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        manager = crawler.addons
        self.assertIsInstance(manager.addons[0], GoodAddon)

    def test_create_instance(self):
        settings_dict = {
            "ADDONS": {"tests.test_addons.CreateInstanceAddon": 0},
            "MYADDON": {"MYADDON_KEY": "val"},
        }
        crawler = get_crawler(settings_dict=settings_dict)
        manager = crawler.addons
        self.assertIsInstance(manager.addons[0], CreateInstanceAddon)
        self.assertEqual(crawler.settings.get("MYADDON_KEY"), "val")
