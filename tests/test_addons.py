import unittest

from scrapy.addons import Addon, AddonManager
from scrapy.settings import BaseSettings


class GoodAddon(object):
    name = "GoodAddon"

    def update_settings(self, config, settings):
        pass

    def check_configuration(self, config, crawler):
        pass


class AddonTest(unittest.TestCase):
    def setUp(self):
        class AddonWithAttributes(Addon):
            name = "Test"

        self.testaddon = AddonWithAttributes()

    def test_export_config(self):
        settings = BaseSettings()
        self.testaddon.config_mapping = {"MAPPED_key": "MAPPING_WORKED"}
        self.testaddon.default_config = {"key": 55, "defaultkey": 100}
        self.testaddon.export_config(
            {"key": 313, "OTHERKEY": True, "mapped_KEY": 99}, settings
        )
        self.assertEqual(settings["KEY"], 313)
        self.assertEqual(settings["DEFAULTKEY"], 100)
        self.assertEqual(settings["OTHERKEY"], True)
        self.assertNotIn("MAPPED_key", settings)
        self.assertNotIn("MAPPED_KEY", settings)
        self.assertEqual(settings["MAPPING_WORKED"], 99)
        self.assertEqual(settings.getpriority("KEY"), 15)

    def test_update_settings(self):
        settings = BaseSettings()
        settings.set("KEY1", "default", priority="default")
        settings.set("KEY2", "project", priority="project")
        addon_config = {"key1": "addon", "key2": "addon", "key3": "addon"}
        self.testaddon.update_settings(addon_config, settings)
        self.assertEqual(settings["KEY1"], "addon")
        self.assertEqual(settings["KEY2"], "project")
        self.assertEqual(settings["KEY3"], "addon")


class AddonManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = AddonManager()

    def test_add(self):
        manager = AddonManager()
        manager.add("tests.test_addons.GoodAddon")
        self.assertCountEqual(manager, ["GoodAddon"])
        self.assertIsInstance(manager["GoodAddon"], GoodAddon)

    def test_load_settings(self):
        settings = BaseSettings()
        settings.set(
            "ADDONS",
            {"tests.test_addons.GoodAddon": 0},
        )
        settings.set("GOODADDON", {"key": "val2"})
        manager = AddonManager()
        manager.load_settings(settings)
        self.assertCountEqual(manager, ["GoodAddon"])
        self.assertIsInstance(manager["GoodAddon"], GoodAddon)
        self.assertCountEqual(manager.configs["GoodAddon"], ["key"])
        self.assertEqual(manager.configs["GoodAddon"]["key"], "val2")
