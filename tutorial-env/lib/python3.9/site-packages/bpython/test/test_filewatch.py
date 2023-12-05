import os
import unittest

try:
    import watchdog
    from bpython.curtsiesfrontend.filewatch import ModuleChangedEventHandler

    has_watchdog = True
except ImportError:
    has_watchdog = False

from unittest import mock


@unittest.skipUnless(has_watchdog, "watchdog required")
class TestModuleChangeEventHandler(unittest.TestCase):
    def setUp(self):
        self.module = ModuleChangedEventHandler([], 1)
        self.module.observer = mock.Mock()

    def test_create_module_handler(self):
        self.assertIsInstance(self.module, ModuleChangedEventHandler)

    def test_add_module(self):
        self.module._add_module("something/test.py")
        self.assertIn(
            os.path.abspath("something/test"),
            self.module.dirs[os.path.abspath("something")],
        )

    def test_activate_throws_error_when_already_activated(self):
        self.module.activated = True
        with self.assertRaises(ValueError):
            self.module.activate()
