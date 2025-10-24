from __future__ import annotations

import argparse
import json
from io import StringIO
from shutil import copytree
from typing import TYPE_CHECKING
from unittest import mock

import pytest

import scrapy
from scrapy.cmdline import _pop_command_name, _print_unknown_command_msg
from scrapy.commands import ScrapyCommand, ScrapyHelpFormatter, view
from scrapy.settings import Settings
from scrapy.utils.reactor import _asyncio_reactor_path
from tests.utils.cmdline import call, proc

if TYPE_CHECKING:
    from pathlib import Path


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
    """A base class for tests that may need a Scrapy project."""

    project_name = "testproject"

    @pytest.fixture(scope="session")
    def _proj_path_cached(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Create a Scrapy project in a temporary directory and return its path.

        Used as a cache for ``proj_path``.
        """
        tmp_path = tmp_path_factory.mktemp("proj")
        call("startproject", self.project_name, cwd=tmp_path)
        return tmp_path / self.project_name

    @pytest.fixture
    def proj_path(self, tmp_path: Path, _proj_path_cached: Path) -> Path:
        """Copy a pre-generated Scrapy project into a temporary directory and return its path."""
        proj_path = tmp_path / self.project_name
        copytree(_proj_path_cached, proj_path)
        return proj_path


class TestCommandCrawlerProcess(TestProjectBase):
    """Test that the command uses the expected kind of *CrawlerProcess
    and produces expected errors when needed."""

    name = "crawl"
    NORMAL_MSG = "Using CrawlerProcess"
    ASYNC_MSG = "Using AsyncCrawlerProcess"

    @pytest.fixture(autouse=True)
    def create_files(self, proj_path: Path) -> None:
        proj_mod_path = proj_path / self.project_name
        (proj_mod_path / "spiders" / "sp.py").write_text("""
import scrapy

class MySpider(scrapy.Spider):
    name = 'sp'

    custom_settings = {}

    async def start(self):
        self.logger.debug('It works!')
        return
        yield
""")

        (proj_mod_path / "spiders" / "aiosp.py").write_text("""
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

        self._append_settings(proj_mod_path, "LOG_LEVEL = 'DEBUG'\n")

    @staticmethod
    def _append_settings(proj_mod_path: Path, text: str) -> None:
        """Add text to the end of the project settings.py."""
        with (proj_mod_path / "settings.py").open("a", encoding="utf-8") as f:
            f.write(text)

    @staticmethod
    def _replace_custom_settings(
        proj_mod_path: Path, spider_name: str, text: str
    ) -> None:
        """Replace custom_settings in the given spider file with the given text."""
        spider_path = proj_mod_path / "spiders" / f"{spider_name}.py"
        with spider_path.open("r+", encoding="utf-8") as f:
            content = f.read()
            content = content.replace(
                "custom_settings = {}", f"custom_settings = {text}"
            )
            f.seek(0)
            f.write(content)
            f.truncate()

    def _assert_spider_works(self, msg: str, proj_path: Path, *args: str) -> None:
        """The command uses the expected *CrawlerProcess, the spider works."""
        _, _, err = proc(self.name, *args, cwd=proj_path)
        assert msg in err
        assert "It works!" in err
        assert "Spider closed (finished)" in err

    def _assert_spider_asyncio_fail(
        self, msg: str, proj_path: Path, *args: str
    ) -> None:
        """The command uses the expected *CrawlerProcess, the spider fails to use asyncio."""
        _, _, err = proc(self.name, *args, cwd=proj_path)
        assert msg in err
        assert "no running event loop" in err

    def test_project_settings(self, proj_path: Path) -> None:
        """The reactor is set via the project default settings (to the asyncio value).

        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        for spider in ["sp", "aiosp"]:
            self._assert_spider_works(self.ASYNC_MSG, proj_path, spider)

    def test_cmdline_asyncio(self, proj_path: Path) -> None:
        """The reactor is set via the command line to the asyncio value.
        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        for spider in ["sp", "aiosp"]:
            self._assert_spider_works(
                self.ASYNC_MSG,
                proj_path,
                spider,
                "-s",
                f"TWISTED_REACTOR={_asyncio_reactor_path}",
            )

    def test_project_settings_explicit_asyncio(self, proj_path: Path) -> None:
        """The reactor explicitly is set via the project settings to the asyncio value.

        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        self._append_settings(
            proj_path / self.project_name,
            f"TWISTED_REACTOR = '{_asyncio_reactor_path}'\n",
        )

        for spider in ["sp", "aiosp"]:
            self._assert_spider_works(self.ASYNC_MSG, proj_path, spider)

    def test_cmdline_empty(self, proj_path: Path) -> None:
        """The reactor is set via the command line to the empty value.

        CrawlerProcess, the default reactor, only the normal spider works."""
        self._assert_spider_works(
            self.NORMAL_MSG, proj_path, "sp", "-s", "TWISTED_REACTOR="
        )
        self._assert_spider_asyncio_fail(
            self.NORMAL_MSG, proj_path, "aiosp", "-s", "TWISTED_REACTOR="
        )

    def test_project_settings_empty(self, proj_path: Path) -> None:
        """The reactor is set via the project settings to the empty value.

        CrawlerProcess, the default reactor, only the normal spider works."""
        self._append_settings(proj_path / self.project_name, "TWISTED_REACTOR = None\n")

        self._assert_spider_works(self.NORMAL_MSG, proj_path, "sp")
        self._assert_spider_asyncio_fail(
            self.NORMAL_MSG, proj_path, "aiosp", "-s", "TWISTED_REACTOR="
        )

    def test_spider_settings_asyncio(self, proj_path: Path) -> None:
        """The reactor is set via the spider settings to the asyncio value.

        AsyncCrawlerProcess, the asyncio reactor, both spiders work."""
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                proj_path / self.project_name,
                spider,
                f"{{'TWISTED_REACTOR': '{_asyncio_reactor_path}'}}",
            )
            self._assert_spider_works(self.ASYNC_MSG, proj_path, spider)

    def test_spider_settings_asyncio_cmdline_empty(self, proj_path: Path) -> None:
        """The reactor is set via the spider settings to the asyncio value
        and via command line to the empty value. The command line value takes
        precedence so the spider settings don't matter.

        CrawlerProcess, the default reactor, only the normal spider works."""
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                proj_path / self.project_name,
                spider,
                f"{{'TWISTED_REACTOR': '{_asyncio_reactor_path}'}}",
            )

        self._assert_spider_works(
            self.NORMAL_MSG, proj_path, "sp", "-s", "TWISTED_REACTOR="
        )
        self._assert_spider_asyncio_fail(
            self.NORMAL_MSG, proj_path, "aiosp", "-s", "TWISTED_REACTOR="
        )

    def test_project_empty_spider_settings_asyncio(self, proj_path: Path) -> None:
        """The reactor is set via the project settings to the empty value
        and via the spider settings to the asyncio value. CrawlerProcess is
        chosen based on the project settings, but the asyncio reactor is chosen
        based on the spider settings.

        CrawlerProcess, the asyncio reactor, both spiders work."""
        self._append_settings(proj_path / self.project_name, "TWISTED_REACTOR = None\n")
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                proj_path / self.project_name,
                spider,
                f"{{'TWISTED_REACTOR': '{_asyncio_reactor_path}'}}",
            )
            self._assert_spider_works(self.NORMAL_MSG, proj_path, spider)

    def test_project_asyncio_spider_settings_select(self, proj_path: Path) -> None:
        """The reactor is set via the project settings to the asyncio value
        and via the spider settings to the select value. AsyncCrawlerProcess
        is chosen based on the project settings, and the conflicting reactor
        setting in the spider settings causes an exception.

        AsyncCrawlerProcess, the asyncio reactor, both spiders produce a
        mismatched reactor exception."""
        self._append_settings(
            proj_path / self.project_name,
            f"TWISTED_REACTOR = '{_asyncio_reactor_path}'\n",
        )
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                proj_path / self.project_name,
                spider,
                "{'TWISTED_REACTOR': 'twisted.internet.selectreactor.SelectReactor'}",
            )
            _, _, err = proc(self.name, spider, cwd=proj_path)
            assert self.ASYNC_MSG in err
            assert (
                "The installed reactor (twisted.internet.asyncioreactor.AsyncioSelectorReactor)"
                " does not match the requested one"
                " (twisted.internet.selectreactor.SelectReactor)"
            ) in err

    def test_project_asyncio_spider_settings_select_forced(
        self, proj_path: Path
    ) -> None:
        """The reactor is set via the project settings to the asyncio value
        and via the spider settings to the select value, CrawlerProcess is
        forced via the project settings. The reactor is chosen based on the
        spider settings.

        CrawlerProcess, the select reactor, only the normal spider works."""
        self._append_settings(
            proj_path / self.project_name, "FORCE_CRAWLER_PROCESS = True\n"
        )
        for spider in ["sp", "aiosp"]:
            self._replace_custom_settings(
                proj_path / self.project_name,
                spider,
                "{'TWISTED_REACTOR': 'twisted.internet.selectreactor.SelectReactor'}",
            )

        self._assert_spider_works(self.NORMAL_MSG, proj_path, "sp")
        self._assert_spider_asyncio_fail(self.NORMAL_MSG, proj_path, "aiosp")


class TestMiscCommands(TestProjectBase):
    def test_list(self, proj_path: Path) -> None:
        assert call("list", cwd=proj_path) == 0

    def test_list_subdir(self, proj_path: Path) -> None:
        """Test that commands work in a subdirectory of the project."""
        subdir = proj_path / "subdir"
        subdir.mkdir(exist_ok=True)
        assert call("list", cwd=subdir) == 0

    def test_command_not_found(self) -> None:
        na_msg = """
The list command is not available from this location.
These commands are only available from within a project: check, crawl, edit, list, parse.
"""
        not_found_msg = """
Unknown command: abc
"""
        params = [
            ("list", False, na_msg),
            ("abc", False, not_found_msg),
            ("abc", True, not_found_msg),
        ]
        for cmdname, inproject, message in params:
            with mock.patch("sys.stdout", new=StringIO()) as out:
                _print_unknown_command_msg(Settings(), cmdname, inproject)
                assert out.getvalue().strip() == message.strip()


class TestBenchCommand:
    def test_run(self) -> None:
        _, _, err = proc(
            "bench",
            "-s",
            "LOGSTATS_INTERVAL=0.001",
            "-s",
            "CLOSESPIDER_TIMEOUT=0.01",
        )
        assert "INFO: Crawled" in err
        assert "Unhandled Error" not in err
        assert "log_count/ERROR" not in err


class TestViewCommand:
    def test_methods(self) -> None:
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


class TestHelpMessage(TestProjectBase):
    COMMANDS = [
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

    def test_help_messages(self, proj_path: Path) -> None:
        for command in self.COMMANDS:
            _, out, _ = proc(command, "-h", cwd=proj_path)
            assert "Usage" in out


class TestPopCommandName:
    def test_valid_command(self) -> None:
        argv = ["scrapy", "crawl", "my_spider"]
        command = _pop_command_name(argv)
        assert command == "crawl"
        assert argv == ["scrapy", "my_spider"]

    def test_no_command(self) -> None:
        argv = ["scrapy"]
        command = _pop_command_name(argv)
        assert command is None
        assert argv == ["scrapy"]

    def test_option_before_command(self) -> None:
        argv = ["scrapy", "-h", "crawl"]
        command = _pop_command_name(argv)
        assert command == "crawl"
        assert argv == ["scrapy", "-h"]

    def test_option_after_command(self) -> None:
        argv = ["scrapy", "crawl", "-h"]
        command = _pop_command_name(argv)
        assert command == "crawl"
        assert argv == ["scrapy", "-h"]
