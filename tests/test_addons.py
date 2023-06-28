import unittest
from typing import Any, Dict, Optional

from scrapy.addons import AddonManager
from scrapy.settings import BaseSettings


class GoodAddon:
    name = "GoodAddon"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.config = config or {}

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
    def setUp(self):
        self.manager = AddonManager()

    def test_add(self):
        manager = AddonManager()
        manager.add("tests.test_addons.GoodAddon")
        self.assertIsInstance(manager.addons[0], GoodAddon)

    def test_load_settings(self):
        settings = BaseSettings()
        settings.set(
            "ADDONS",
            {"tests.test_addons.GoodAddon": 0},
        )
        settings.set("GOODADDON", {"key": "val2"})
        manager = AddonManager()
        manager.load_settings(settings)
        self.assertIsInstance(manager.addons[0], GoodAddon)
