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
from typing import Any
from unittest import mock

import pytest

import scrapy
from scrapy.cmdline import _pop_command_name, _print_unknown_command_msg
from scrapy.commands import ScrapyCommand, ScrapyHelpFormatter, view
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.reactor import _asyncio_reactor_path
from scrapy.utils.test import get_testenv


class EmptyCommand(ScrapyCommand):
    def short_desc(self) -> str:
        return ""

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        pass


class TestCommandSettings:
    def setup_method(self):
        self.command = EmptyCommand()
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


class TestProjectBase:
    project_name = "testproject"

    def setup_method(self):
        self.temp_path = mkdtemp()
        self.cwd = self.temp_path
        self.proj_path = Path(self.temp_path, self.project_name)
        self.proj_mod_path = self.proj_path / self.project_name
        self.env = get_testenv()

    def teardown_method(self):
        rmtree(self.temp_path)

    def call(self, *args: str, **popen_kwargs: Any) -> int:
        with TemporaryFile() as out:
            args = (sys.executable, "-m", "scrapy.cmdline", *args)
            return subprocess.call(
                args, stdout=out, stderr=out, cwd=self.cwd, env=self.env, **popen_kwargs
            )

    def proc(
        self, *args: str, **popen_kwargs: Any
    ) -> tuple[subprocess.Popen[bytes], str, str]:
        args = (sys.executable, "-m", "scrapy.cmdline", *args)
        p = subprocess.Popen(
            args,
            cwd=popen_kwargs.pop("cwd", self.cwd),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_kwargs,
        )

        try:
            stdout, stderr = p.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            pytest.fail("Command took too much time to complete")

        return p, to_unicode(stdout), to_unicode(stderr)

    @staticmethod
    def find_in_file(filename: Path, regex: str) -> re.Match | None:
        """Find first pattern occurrence in file"""
        pattern = re.compile(regex)
        with filename.open("r", encoding="utf-8") as f:
            for line in f:
                match = pattern.search(line)
                if match is not None:
                    return match
        return None


class TestCommandBase(TestProjectBase):
    def setup_method(self):
        super().setup_method()
        self.call("startproject", self.project_name)
        self.cwd = self.proj_path
        self.env["SCRAPY_SETTINGS_MODULE"] = f"{self.project_name}.settings"


class TestCommandCrawlerProcess(TestCommandBase):
    """Test that the command uses the expected kind of *CrawlerProcess
    and produces expected errors when needed."""

    name = "crawltest"

    NORMAL_MSG = "Type of self.crawler_process: <class 'scrapy.crawler.CrawlerProcess'>"
    ASYNC_MSG = (
        "Type of self.crawler_process: <class 'scrapy.crawler.AsyncCrawlerProcess'>"
    )

    def setup_method(self):
        super().setup_method()
        (self.cwd / self.project_name / "commands").mkdir(exist_ok=True)
        (self.cwd / self.project_name / "commands" / "__init__.py").touch()
        (self.cwd / self.project_name / "commands" / f"{self.name}.py").write_text("""
from scrapy.commands.crawl import Command

class CrawlerProcessCrawlCommand(Command):
    requires_project = True

    def run(self, args, opts):
        print(f"Type of self.crawler_process: {type(self.crawler_process)}")
        super().run(args, opts)
""")

        self._append_settings(f"COMMANDS_MODULE = '{self.project_name}.commands'\n")

        (self.cwd / self.project_name / "spiders" / "sp.py").write_text("""
import scrapy

class MySpider(scrapy.Spider):
    name = 'sp'

    custom_settings = {}

    async def start(self):
        self.logger.debug('It works!')
        return
        yield
""")

        (self.cwd / self.project_name / "spiders" / "aiosp.py").write_text("""
import asyncio

import scrapy

class MySpider(scrapy.Spider):
    name = 'aiosp'

    custom_settings = {}

    async def start(self):
        await asyncio.sleep(0.01)
        self.logger.debug('It works!')
        return
        yield
""")

    def _append_settings(self, text: str) -> None:
        """Add text to the end of the project settings.py."""
        with (self.cwd / self.project_name / "settings.py").open(
            "a", encoding="utf-8"
        ) as f:
            f.write(text)

    def _replace_custom_settings(self, spider_name: str, text: str) -> None:
        """Replace custom_settings in the given spider file with the given text."""
        spider_path = self.cwd / self.project_name / "spiders" / f"{spider_name}.py"
        with spider_path.open("r+", encoding="utf-8") as f:
            content = f.read()
            content = content.replace(
                "custom_settings = {}", f"custom_settings = {text}"
            )
            f.seek(0)
            f.write(content)
            f.truncate()

    def _assert_spider_works(self, msg: str, *args: str) -> None:
        """The command uses the expected *CrawlerProcess, the spider works."""
        _, out, err = self.proc(self.name, *args)
        assert msg in out, out
        assert "It works!" in err, err
        assert "Spider closed (finished)" in err, err

    def _assert_spider_asyncio_fail(self, msg: str, *args: str) -> None:
        """The command uses the expected *CrawlerProcess, the spider fails to use asyncio."""
        _, out, err = self.proc(self.name, *args)
        assert msg in out, out
        assert "no running event loop" in err, err

    def test_project_settings(self):
        """The reactor is set via the project default settings (to the asyncio value).

        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        for spider in ["sp", "aiosp"]:
            self._assert_spider_works(self.ASYNC_MSG, spider)

    def test_cmdline_asyncio(self):
        """The reactor is set via the command line to the asyncio value.
        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        for spider in ["sp", "aiosp"]:
            self._assert_spider_works(
                self.ASYNC_MSG, spider, "-s", f"TWISTED_REACTOR={_asyncio_reactor_path}"
            )

    def test_project_settings_explicit_asyncio(self):
        """The reactor explicitly is set via the project settings to the asyncio value.

        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        self._append_settings(f"TWISTED_REACTOR = '{_asyncio_reactor_path}'\n")

        for spider in ["sp", "aiosp"]:
            self._assert_spider_works(self.ASYNC_MSG, spider)

    def test_cmdline_empty(self):
        """The reactor is set via the command line to the empty value.

        CrawlerProcess, the default reactor, only the normal spider works."""
        self._assert_spider_works(self.NORMAL_MSG, "sp", "-s", "TWISTED_REACTOR=")
        self._assert_spider_asyncio_fail(
            self.NORMAL_MSG, "aiosp", "-s", "TWISTED_REACTOR="
        )

    def test_project_settings_empty(self):
        """The reactor is set via the project settings to the empty value.

        CrawlerProcess, the default reactor, only the normal spider works."""
        self._append_settings("TWISTED_REACTOR = None\n")

        self._assert_spider_works(self.NORMAL_MSG, "sp")
        self._assert_spider_asyncio_fail(
            self.NORMAL_MSG, "aiosp", "-s", "TWISTED_REACTOR="
        )

    def test_spider_settings_asyncio(self):
        """The reactor is set via the spider settings to the asyncio value.

        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                spider, f"{{'TWISTED_REACTOR': '{_asyncio_reactor_path}'}}"
            )
            self._assert_spider_works(self.ASYNC_MSG, spider)

    def test_spider_settings_asyncio_cmdline_empty(self):
        """The reactor is set via the spider settings to the asyncio value
        and via command line to the empty value. The command line value takes
        precedence so the spider settings don't matter.

        CrawlerProcess, the default reactor, only the normal spider works."""
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                spider, f"{{'TWISTED_REACTOR': '{_asyncio_reactor_path}'}}"
            )

        self._assert_spider_works(self.NORMAL_MSG, "sp", "-s", "TWISTED_REACTOR=")
        self._assert_spider_asyncio_fail(
            self.NORMAL_MSG, "aiosp", "-s", "TWISTED_REACTOR="
        )

    def test_project_empty_spider_settings_asyncio(self):
        """The reactor is set via the project settings to the empty value
        and via the spider settings to the asyncio value. CrawlerProcess is
        chosen based on the project settings, but the asyncio reactor is chosen
        based on the spider settings.

        CrawlerProcess, the asyncio reactor, both spiders work."""
        self._append_settings("TWISTED_REACTOR = None\n")
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                spider, f"{{'TWISTED_REACTOR': '{_asyncio_reactor_path}'}}"
            )
            self._assert_spider_works(self.NORMAL_MSG, spider)

    def test_project_asyncio_spider_settings_select(self):
        """The reactor is set via the project settings to the asyncio value
        and via the spider settings to the select value. AsyncCrawlerProcess
        is chosen based on the project settings, and the conflicting reactor
        setting in the spider settings causes an exception.

        AsyncCrawlerProcess, the asyncio reactor, both spiders produce a
        mismatched reactor exception."""
        self._append_settings(f"TWISTED_REACTOR = '{_asyncio_reactor_path}'\n")
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                spider,
                "{'TWISTED_REACTOR': 'twisted.internet.selectreactor.SelectReactor'}",
            )
            _, out, err = self.proc(self.name, spider)
            assert self.ASYNC_MSG in out, out
            assert (
                "The installed reactor (twisted.internet.asyncioreactor.AsyncioSelectorReactor)"
                " does not match the requested one"
                " (twisted.internet.selectreactor.SelectReactor)"
            ) in err, err

    def test_project_asyncio_spider_settings_select_forced(self):
        """The reactor is set via the project settings to the asyncio value
        and via the spider settings to the select value, CrawlerProcess is
        forced via the project settings. The reactor is chosen based on the
        spider settings.

        CrawlerProcess, the select reactor, only the normal spider works."""
        self._append_settings("FORCE_CRAWLER_PROCESS = True\n")
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                spider,
                "{'TWISTED_REACTOR': 'twisted.internet.selectreactor.SelectReactor'}",
            )

        self._assert_spider_works(self.NORMAL_MSG, "sp")
        self._assert_spider_asyncio_fail(self.NORMAL_MSG, "aiosp")


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


class TestProjectSubdir(TestProjectBase):
    """Test that commands work in a subdirectory of the project."""

    def setup_method(self):
        super().setup_method()
        self.call("startproject", self.project_name)
        self.cwd = self.proj_path / "subdir"
        self.cwd.mkdir(exist_ok=True)

    def test_list(self):
        assert self.call("list") == 0


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
    def setup_method(self):
        super().setup_method()
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
