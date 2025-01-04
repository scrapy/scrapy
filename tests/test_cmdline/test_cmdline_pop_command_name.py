from twisted.trial import unittest

from scrapy.cmdline import _pop_command_name


class PopCommandNameTestCase(unittest.TestCase):
    def test_valid_command(self):
        argv = ["scrapy", "crawl", "my_spider"]
        command = _pop_command_name(argv)
        self.assertEqual(command, "crawl")
        self.assertEqual(argv, ["scrapy", "my_spider"])

    def test_no_command(self):
        argv = ["scrapy"]
        command = _pop_command_name(argv)
        self.assertIsNone(command)
        self.assertEqual(argv, ["scrapy"])

    def test_option_before_command(self):
        argv = ["scrapy", "-h", "crawl"]
        command = _pop_command_name(argv)
        self.assertEqual(command, "crawl")
        self.assertEqual(argv, ["scrapy", "-h"])

    def test_option_after_command(self):
        argv = ["scrapy", "crawl", "-h"]
        command = _pop_command_name(argv)
        self.assertEqual(command, "crawl")
        self.assertEqual(argv, ["scrapy", "-h"])
