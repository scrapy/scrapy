from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from io import StringIO
from pathlib import Path
from shutil import rmtree
from tempfile import TemporaryFile, mkdtemp
from threading import Timer
from typing import TYPE_CHECKING
from unittest import mock

from twisted.trial import unittest

import scrapy
from scrapy.cmdline import _pop_command_name, _print_unknown_command_msg
from scrapy.commands import ScrapyCommand, ScrapyHelpFormatter, view
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_testenv

if TYPE_CHECKING:
    import os


class TestCommandSettings:
    def setup_method(self):
        self.command = ScrapyCommand()
        self.command.settings = Settings()
        self.parser = argparse.ArgumentParser(
            formatter_class=ScrapyHelpFormatter, conflict_handler="resolve"
        )
        self.command.add_options(self.parser)

    def test_settings_json_string(self):
        feeds_json = '{"data.json": {"format": "json"}, "data.xml": {"format": "xml"}}'
        opts, args = self.parser.parse_known_args(
            args=["-s", f"FEEDS={feeds_json}", "spider.py"]
        )
        self.command.process_options(args, opts)
        assert isinstance(self.command.settings["FEEDS"], scrapy.settings.BaseSettings)
        assert dict(self.command.settings["FEEDS"]) == json.loads(feeds_json)

    def test_help_formatter(self):
        formatter = ScrapyHelpFormatter(prog="scrapy")
        part_strings = [
            "usage: scrapy genspider [options] <name> <domain>\n\n",
            "\n",
            "optional arguments:\n",
            "\n",
            "Global Options:\n",
        ]
        assert formatter._join_parts(part_strings) == (
            "Usage\n=====\n  scrapy genspider [options] <name> <domain>\n\n\n"
            "Optional Arguments\n==================\n\n"
            "Global Options\n--------------\n"
        )


class TestProjectBase(unittest.TestCase):
    project_name = "testproject"

    def setUp(self):
        self.temp_path = mkdtemp()
        self.cwd = self.temp_path
        self.proj_path = Path(self.temp_path, self.project_name)
        self.proj_mod_path = self.proj_path / self.project_name
        self.env = get_testenv()

    def tearDown(self):
        rmtree(self.temp_path)

    def call(self, *new_args, **kwargs):
        with TemporaryFile() as out:
            args = (sys.executable, "-m", "scrapy.cmdline", *new_args)
            return subprocess.call(
                args, stdout=out, stderr=out, cwd=self.cwd, env=self.env, **kwargs
            )

    def proc(self, *new_args, **popen_kwargs):
        args = (sys.executable, "-m", "scrapy.cmdline", *new_args)
        p = subprocess.Popen(
            args,
            cwd=popen_kwargs.pop("cwd", self.cwd),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_kwargs,
        )

        def kill_proc():
            p.kill()
            p.communicate()
            raise AssertionError("Command took too much time to complete")

        timer = Timer(15, kill_proc)
        try:
            timer.start()
            stdout, stderr = p.communicate()
        finally:
            timer.cancel()

        return p, to_unicode(stdout), to_unicode(stderr)

    def find_in_file(self, filename: str | os.PathLike, regex) -> re.Match | None:
        """Find first pattern occurrence in file"""
        pattern = re.compile(regex)
        with Path(filename).open("r", encoding="utf-8") as f:
            for line in f:
                match = pattern.search(line)
                if match is not None:
                    return match
        return None


class TestCommandBase(TestProjectBase):
    def setUp(self):
        super().setUp()
        self.call("startproject", self.project_name)
        self.cwd = Path(self.temp_path, self.project_name)
        self.env["SCRAPY_SETTINGS_MODULE"] = f"{self.project_name}.settings"


class TestMiscCommands(TestCommandBase):
    def test_list(self):
        assert self.call("list") == 0

    def test_command_not_found(self):
        na_msg = """
The list command is not available from this location.
These commands are only available from within a project: check, crawl, edit, list, parse.
"""
        not_found_msg = """
Unknown command: abc
"""
        params = [
            ("list", 0, na_msg),
            ("abc", 0, not_found_msg),
            ("abc", 1, not_found_msg),
        ]
        for cmdname, inproject, message in params:
            with mock.patch("sys.stdout", new=StringIO()) as out:
                _print_unknown_command_msg(Settings(), cmdname, inproject)
                assert out.getvalue().strip() == message.strip()


class TestBenchCommand(TestCommandBase):
    def test_run(self):
        _, _, log = self.proc(
            "bench", "-s", "LOGSTATS_INTERVAL=0.001", "-s", "CLOSESPIDER_TIMEOUT=0.01"
        )
        assert "INFO: Crawled" in log
        assert "Unhandled Error" not in log
        assert "log_count/ERROR" not in log


class TestViewCommand(TestCommandBase):
    def test_methods(self):
        command = view.Command()
        command.settings = Settings()
        parser = argparse.ArgumentParser(
            prog="scrapy",
            prefix_chars="-",
            formatter_class=ScrapyHelpFormatter,
            conflict_handler="resolve",
        )
        command.add_options(parser)
        assert command.short_desc() == "Open URL in browser, as seen by Scrapy"
        assert "URL using the Scrapy downloader and show its" in command.long_desc()


class TestHelpMessage(TestCommandBase):
    def setUp(self):
        super().setUp()
        self.commands = [
            "parse",
            "startproject",
            "view",
            "crawl",
            "edit",
            "list",
            "fetch",
            "settings",
            "shell",
            "runspider",
            "version",
            "genspider",
            "check",
            "bench",
        ]

    def test_help_messages(self):
        for command in self.commands:
            _, out, _ = self.proc(command, "-h")
            assert "Usage" in out


class TestPopCommandName:
    def test_valid_command(self):
        argv = ["scrapy", "crawl", "my_spider"]
        command = _pop_command_name(argv)
        assert command == "crawl"
        assert argv == ["scrapy", "my_spider"]

    def test_no_command(self):
        argv = ["scrapy"]
        command = _pop_command_name(argv)
        assert command is None
        assert argv == ["scrapy"]

    def test_option_before_command(self):
        argv = ["scrapy", "-h", "crawl"]
        command = _pop_command_name(argv)
        assert command == "crawl"
        assert argv == ["scrapy", "-h"]

    def test_option_after_command(self):
        argv = ["scrapy", "crawl", "-h"]
        command = _pop_command_name(argv)
        assert command == "crawl"
        assert argv == ["scrapy", "-h"]
