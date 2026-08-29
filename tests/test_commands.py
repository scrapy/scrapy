from __future__ import annotations

import argparse
import json
import pdb  # noqa: T100
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from twisted.python import failure

import scrapy
from scrapy.cmdline import _pop_command_name, execute
from scrapy.commands import ScrapyCommand, ScrapyHelpFormatter
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import Settings
from scrapy.utils.reactor import _asyncio_reactor_path
from tests.utils.bases.commands import TestProjectBase
from tests.utils.cmdline import (
    call,
    proc,
    write_recording_browser,
    write_recording_editor,
)

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class EmptyCommand(ScrapyCommand):
    def short_desc(self) -> str:
        return ""

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        pass


class TestHelpDeprecation:
    def test_calling_help_is_deprecated(self) -> None:
        command = EmptyCommand()
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"ScrapyCommand\.help\(\) is deprecated, use long_desc\(\) instead\.",
        ):
            result = command.help()
        # help() still delegates to long_desc() for backward compatibility.
        assert result == command.long_desc()

    def test_overriding_help_is_deprecated(self) -> None:
        class HelpCommand(ScrapyCommand):
            def short_desc(self) -> str:
                return ""

            def run(self, args: list[str], opts: argparse.Namespace) -> None:
                pass

            def help(self) -> str:
                return "custom help"

        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"The ScrapyCommand\.help\(\) method is deprecated and "
            r"overriding it, as the .*HelpCommand class does, has no effect; "
            r"override long_desc\(\) instead\.",
        ):
            HelpCommand()

    def test_not_overriding_help_does_not_warn(self, recwarn) -> None:
        # Commands that do not override help() must not emit the
        # override-deprecation warning when instantiated, including subclasses
        # several levels below ScrapyCommand (as the built-in commands are).
        class SubCommand(EmptyCommand):
            pass

        EmptyCommand()
        SubCommand()
        assert not [
            w for w in recwarn.list if issubclass(w.category, ScrapyDeprecationWarning)
        ]


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
        assert self.command.settings is not None
        assert isinstance(self.command.settings["FEEDS"], scrapy.settings.BaseSettings)
        assert dict(self.command.settings["FEEDS"]) == json.loads(feeds_json)

    def test_pdb_uses_ipdb_if_installed(self, monkeypatch):
        monkeypatch.setattr(failure, "startDebugMode", lambda: None)
        fake_ipdb: Any = argparse.Namespace(post_mortem=lambda tb: None)
        monkeypatch.setitem(sys.modules, "pdb", pdb)
        monkeypatch.setitem(sys.modules, "ipdb", fake_ipdb)
        opts, args = self.parser.parse_known_args(args=["--pdb", "spider.py"])
        self.command.process_options(args, opts)
        assert sys.modules["pdb"] is fake_ipdb

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


class TestGlobalOptions:
    """Tests for the options that every command supports."""

    spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = "myspider"

    async def start(self):
        self.logger.debug("It works!")
        return
        yield
"""

    @pytest.fixture
    def spider_path(self, tmp_path: Path) -> Path:
        path = tmp_path / "myspider.py"
        path.write_text(self.spider_code, encoding="utf-8")
        return path

    def test_invalid_set(self, spider_path: Path) -> None:
        returncode, _, err = proc("runspider", str(spider_path), "-s", "FOO")
        assert returncode == 2
        assert "Invalid -s value, use -s NAME=VALUE" in err

    def test_invalid_spider_argument(self, spider_path: Path) -> None:
        returncode, _, err = proc("runspider", str(spider_path), "-a", "FOO")
        assert returncode == 2
        assert "Invalid -a value, use -a NAME=VALUE" in err

    def test_logfile(self, tmp_path: Path, spider_path: Path) -> None:
        logfile = tmp_path / "scrapy.log"
        returncode, _, err = proc(
            "runspider", str(spider_path), "--logfile", str(logfile)
        )
        assert returncode == 0, err
        assert "It works!" in logfile.read_text(encoding="utf-8")
        assert "It works!" not in err

    def test_loglevel(self, spider_path: Path) -> None:
        returncode, _, err = proc("runspider", str(spider_path), "--loglevel", "INFO")
        assert returncode == 0, err
        assert "It works!" not in err
        assert "Spider closed (finished)" in err

    def test_nolog(self, spider_path: Path) -> None:
        returncode, _, err = proc("runspider", str(spider_path), "--nolog")
        assert returncode == 0, err
        assert not err

    def test_pidfile(self, tmp_path: Path, spider_path: Path) -> None:
        pidfile = tmp_path / "scrapy.pid"
        returncode, _, err = proc(
            "runspider", str(spider_path), "--pidfile", str(pidfile)
        )
        assert returncode == 0, err
        assert pidfile.read_text(encoding="utf-8").strip().isdigit()

    def test_pdb(self, spider_path: Path) -> None:
        returncode, _, err = proc("runspider", str(spider_path), "--pdb")
        assert returncode == 0, err
        assert "It works!" in err


class TestSettingsCommand:
    @pytest.mark.parametrize(
        ("option", "setting", "expected"),
        [
            ("--get", "BOT_NAME", "scrapybot"),
            ("--getbool", "COOKIES_ENABLED", "True"),
            ("--getint", "CONCURRENT_REQUESTS", "16"),
            ("--getfloat", "DOWNLOAD_DELAY", "0.0"),
            ("--getlist", "SPIDER_MODULES", "[]"),
        ],
    )
    def test_get(self, option: str, setting: str, expected: str) -> None:
        returncode, out, err = proc("settings", option, setting)
        assert returncode == 0, err
        assert out.startswith(expected)

    def test_no_option(self) -> None:
        returncode, out, err = proc("settings")
        assert returncode == 0, err
        assert not out


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
        self._assert_spider_asyncio_fail(self.NORMAL_MSG, proj_path, "aiosp")

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


class TestCommandListing(TestProjectBase):
    """Tests for the command list that ``scrapy`` prints when called without a
    command name."""

    def test_outside_project(self) -> None:
        returncode, out, err = proc()
        assert returncode == 0, err
        assert f"Scrapy {scrapy.__version__} - no active project" in out
        assert "Available commands:" in out
        assert "Create new project" in out
        assert "More commands available when run from project directory" in out
        assert 'Use "scrapy <command> -h" to see more info about a command' in out

    def test_inside_project(self, proj_path: Path) -> None:
        returncode, out, err = proc(cwd=proj_path)
        assert returncode == 0, err
        assert (
            f"Scrapy {scrapy.__version__} - active project: {self.project_name}" in out
        )
        assert "List available spiders" in out
        assert "More commands available when run from project directory" not in out


class TestUnknownCommand(TestProjectBase):
    def test_outside_project(self) -> None:
        returncode, out, err = proc("abc")
        assert returncode == 2, err
        assert f"Scrapy {scrapy.__version__} - no active project" in out
        assert "Unknown command: abc" in out
        assert 'Use "scrapy" to see available commands' in out

    def test_inside_project(self, proj_path: Path) -> None:
        returncode, out, err = proc("abc", cwd=proj_path)
        assert returncode == 2, err
        assert (
            f"Scrapy {scrapy.__version__} - active project: {self.project_name}" in out
        )
        assert "Unknown command: abc" in out

    def test_project_only_command_outside_project(self) -> None:
        returncode, out, err = proc("list")
        assert returncode == 2, err
        assert "The list command is not available from this location." in out
        assert (
            "These commands are only available from within a project: "
            "check, crawl, edit, list, parse." in out
        )


class TestCommandsModule(TestProjectBase):
    """Tests for commands defined in the module of the COMMANDS_MODULE setting."""

    @pytest.fixture
    def proj_path_with_commands(self, proj_path: Path) -> Path:
        commands_path = proj_path / self.project_name / "commands"
        commands_path.mkdir()
        (commands_path / "__init__.py").touch()
        (commands_path / "mycmd.py").write_text(
            """
from scrapy.commands import ScrapyCommand


class Command(ScrapyCommand):
    requires_crawler_process = False

    def short_desc(self):
        return "My custom command"

    def run(self, args, opts):
        print("My custom command ran")
""",
            encoding="utf-8",
        )
        (commands_path / "helpcmd.py").write_text(
            """
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):
    requires_crawler_process = False

    def short_desc(self):
        return "My command that asks for its help message"

    def run(self, args, opts):
        raise UsageError
""",
            encoding="utf-8",
        )
        (commands_path / "silentcmd.py").write_text(
            """
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):
    requires_crawler_process = False

    def short_desc(self):
        return "My command that fails silently"

    def run(self, args, opts):
        raise UsageError(print_help=False)
""",
            encoding="utf-8",
        )
        self._append_settings(
            proj_path / self.project_name,
            f'\nCOMMANDS_MODULE = "{self.project_name}.commands"\n',
        )
        return proj_path

    def test_listed(self, proj_path_with_commands: Path) -> None:
        returncode, out, err = proc(cwd=proj_path_with_commands)
        assert returncode == 0, err
        assert "My custom command" in out

    def test_run(self, proj_path_with_commands: Path) -> None:
        returncode, out, err = proc("mycmd", cwd=proj_path_with_commands)
        assert returncode == 0, err
        assert "My custom command ran" in out

    def test_usage_error(self, proj_path_with_commands: Path) -> None:
        """A message-less UsageError makes the help message be printed."""
        returncode, out, err = proc("helpcmd", cwd=proj_path_with_commands)
        assert returncode == 2, err
        assert "scrapy helpcmd" in out

    def test_usage_error_without_help(self, proj_path_with_commands: Path) -> None:
        """A message-less UsageError with print_help disabled prints nothing."""
        returncode, out, err = proc("silentcmd", cwd=proj_path_with_commands)
        assert returncode == 2, err
        assert not out


class TestEntryPointCommands:
    """Tests for commands defined in the scrapy.commands entry point group."""

    @staticmethod
    def _write_dist(path: Path, entry_point: str) -> None:
        """Write into *path* a package with a command and a function, and the
        metadata of an installed distribution that declares *entry_point* in
        the scrapy.commands entry point group.

        Since ``python -m scrapy.cmdline`` puts the current working directory
        in the import path, running it with *path* as the working directory
        makes Scrapy find that entry point.
        """
        package_path = path / "mycmds"
        package_path.mkdir()
        (package_path / "__init__.py").touch()
        (package_path / "mycmd.py").write_text(
            """
from scrapy.commands import ScrapyCommand


class Command(ScrapyCommand):
    requires_crawler_process = False

    def short_desc(self):
        return "My entry point command"

    def run(self, args, opts):
        print("My entry point command ran")


def not_a_command():
    pass
""",
            encoding="utf-8",
        )
        dist_info_path = path / "mycmds-1.0.dist-info"
        dist_info_path.mkdir()
        (dist_info_path / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: mycmds\nVersion: 1.0\n", encoding="utf-8"
        )
        (dist_info_path / "entry_points.txt").write_text(
            f"[scrapy.commands]\n{entry_point}\n", encoding="utf-8"
        )

    def test_listed(self, tmp_path: Path) -> None:
        self._write_dist(tmp_path, "mycmd = mycmds.mycmd:Command")
        returncode, out, err = proc(cwd=tmp_path)
        assert returncode == 0, err
        assert "My entry point command" in out

    def test_run(self, tmp_path: Path) -> None:
        self._write_dist(tmp_path, "mycmd = mycmds.mycmd:Command")
        returncode, out, err = proc("mycmd", cwd=tmp_path)
        assert returncode == 0, err
        assert "My entry point command ran" in out

    def test_not_a_class(self, tmp_path: Path) -> None:
        self._write_dist(tmp_path, "mycmd = mycmds.mycmd:not_a_command")
        returncode, _, err = proc("version", cwd=tmp_path)
        assert returncode == 1
        assert "ValueError: Invalid entry point mycmd" in err


class TestExecute:
    """Tests for calls to scrapy.cmdline.execute() from Python code, which the
    command line does not cover."""

    def test_argv(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            execute(["scrapy", "version"])
        assert exc_info.value.code == 0
        assert scrapy.__version__ in capsys.readouterr().out

    def test_settings(self, capsys: pytest.CaptureFixture[str]) -> None:
        settings = Settings()
        with pytest.raises(SystemExit) as exc_info:
            execute(["scrapy", "settings", "--get", "BOT_NAME"], settings=settings)
        assert exc_info.value.code == 0
        assert capsys.readouterr().out.strip() == "scrapybot"


class TestBenchCommand:
    @pytest.mark.parametrize("use_reactor", [True, False])
    def test_run(self, use_reactor: bool) -> None:
        args: list[str] = [
            "bench",
            "-s",
            "LOGSTATS_INTERVAL=0.001",
            "-s",
            "CLOSESPIDER_TIMEOUT=0.01",
        ]
        if not use_reactor:
            args += ["-s", "TWISTED_REACTOR_ENABLED=False"]
        _, _, err = proc(*args)
        assert "INFO: Crawled" in err
        assert "Unhandled Error" not in err
        assert "log_count/ERROR" not in err


class TestViewCommand:
    @pytest.mark.skipif(
        sys.platform == "win32", reason="requires a POSIX shell browser script"
    )
    def test_view(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mockserver: MockServer
    ) -> None:
        opened = tmp_path / "opened.txt"
        browser = tmp_path / "fake-browser.sh"
        write_recording_browser(browser, opened)
        monkeypatch.setenv("BROWSER", str(browser))

        returncode, _, err = proc("view", mockserver.url("/html"), cwd=tmp_path)

        assert returncode == 0, err
        url = opened.read_text(encoding="utf-8")
        assert url.startswith("file://")
        body = Path(url.removeprefix("file://")).read_text(encoding="utf-8")
        assert "<p class='one'>Works</p>" in body

    def test_non_text_response(self, mockserver: MockServer) -> None:
        returncode, _, err = proc(
            "view", mockserver.url("/static/files/images/scrapy.png")
        )
        assert returncode == 0, err
        assert "Cannot view a non-text response." in err


class TestEditCommand(TestProjectBase):
    @pytest.mark.skipif(
        sys.platform == "win32", reason="requires a POSIX shell editor script"
    )
    def test_edit(self, proj_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        spider = proj_path / self.project_name / "spiders" / "example.py"
        edited = proj_path / "edited.txt"
        editor = proj_path / "fake-editor.sh"
        write_recording_editor(editor)
        monkeypatch.setenv("EDITOR", f"{editor} {edited}")

        assert call("genspider", "example", "example.com", cwd=proj_path) == 0
        returncode, _, err = proc("edit", "example", cwd=proj_path)

        assert returncode == 0, err
        assert (proj_path / edited.read_text(encoding="utf-8")).resolve() == (
            spider.resolve()
        )

    def test_edit_spider_not_found(self, proj_path: Path) -> None:
        returncode, _, err = proc("edit", "nonexistent", cwd=proj_path)
        assert returncode == 1
        assert "Spider not found: nonexistent" in err

    def test_edit_no_spider(self, proj_path: Path) -> None:
        returncode, out, _ = proc("edit", cwd=proj_path)
        assert returncode == 2
        assert "Usage" in out


class TestHelpMessage(TestProjectBase):
    @pytest.mark.parametrize(
        "command",
        [
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
        ],
    )
    def test_help_messages(self, proj_path: Path, command: str) -> None:
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
