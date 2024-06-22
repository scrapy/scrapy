import argparse
import unittest
from unittest.mock import patch

from scrapy.commands.settings import Command
from scrapy.settings import BaseSettings, Settings


class SettingCommandTest(unittest.TestCase):

    def setUp(self):
        self.test_command = Command()
        self.test_command.settings = Settings(self.test_command.default_settings)
        self.test_command.crawler_process = type("", (), {})()
        self.test_command.crawler_process.settings = Settings(
            {
                "LOG_LEVEL": "INFO",
                "testBaseSetting": BaseSettings(
                    {"test_nested_key": "test_nested_value"}
                ),
                "testNotBaseSetting": "test_value",
                "testBoolSetting": True,
                "testIntSetting": 42,
                "testFloatSetting": 3.14,
                "testListSetting": ["one", "two", "three"],
            }
        )

    @patch("builtins.print")
    def test_get_base_setting(self, mock_print):
        parser = argparse.ArgumentParser()
        self.test_command.add_options(parser)
        args = parser.parse_args(["--get", "testBaseSetting"])
        self.test_command.run([], args)
        mock_print.assert_called_with('{"test_nested_key": "test_nested_value"}')

    @patch("builtins.print")
    def test_get_not_base_setting(self, mock_print):
        parser = argparse.ArgumentParser()
        self.test_command.add_options(parser)
        args = parser.parse_args(["--get", "testNotBaseSetting"])
        self.test_command.run([], args)
        mock_print.assert_called_with("test_value")

    @patch("builtins.print")
    def test_get_bool_setting(self, mock_print):
        parser = argparse.ArgumentParser()
        self.test_command.add_options(parser)
        args = parser.parse_args(["--getbool", "testBoolSetting"])
        self.test_command.run([], args)
        mock_print.assert_called_with(True)

    @patch("builtins.print")
    def test_get_int_setting(self, mock_print):
        parser = argparse.ArgumentParser()
        self.test_command.add_options(parser)
        args = parser.parse_args(["--getint", "testIntSetting"])
        self.test_command.run([], args)
        mock_print.assert_called_with(42)

    @patch("builtins.print")
    def test_get_float_setting(self, mock_print):
        parser = argparse.ArgumentParser()
        self.test_command.add_options(parser)
        args = parser.parse_args(["--getfloat", "testFloatSetting"])
        self.test_command.run([], args)
        mock_print.assert_called_with(3.14)

    @patch("builtins.print")
    def test_get_list_setting(self, mock_print):
        parser = argparse.ArgumentParser()
        self.test_command.add_options(parser)
        args = parser.parse_args(["--getlist", "testListSetting"])
        self.test_command.run([], args)
        mock_print.assert_called_with(["one", "two", "three"])

    @patch("builtins.print")
    def test_default_setting(self, mock_print):
        parser = argparse.ArgumentParser()
        self.test_command.add_options(parser)
        args = parser.parse_args([])
        self.test_command.run([], args)
        mock_print.assert_not_called()


if __name__ == "__main__":
    unittest.main()
