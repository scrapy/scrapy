from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.utils.bases.commands import TestProjectBase
from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from pathlib import Path


def candidates(*words: str, cwd: Path | None = None) -> list[str]:
    """Return the completion values offered for the last of *words*."""
    returncode, out, err = proc("complete", "--", *words, cwd=cwd)
    assert returncode == 0, err
    return [line.partition("\t")[0] for line in out.splitlines()]


class TestScripts:
    @pytest.mark.parametrize("shell", ["bash", "fish", "zsh"])
    def test_output(self, shell: str) -> None:
        returncode, out, err = proc("complete", shell)
        assert returncode == 0, err
        assert "scrapy complete --" in out

    @pytest.mark.parametrize("args", [(), ("csh",), ("bash", "zsh")])
    def test_usage_error(self, args: tuple[str, ...]) -> None:
        returncode, out, _ = proc("complete", *args)
        assert returncode == 2
        assert "scrapy complete <bash|fish|zsh>" in out


class TestCommandNames:
    def test_all(self) -> None:
        values = candidates("")
        assert "complete" in values
        assert "startproject" in values

    def test_prefix(self) -> None:
        assert candidates("ver") == ["version"]

    def test_descriptions(self) -> None:
        _, out, _ = proc("complete", "--", "version")
        assert out.strip() == "version\tPrint Scrapy version"

    def test_unknown_command(self) -> None:
        assert candidates("nosuchcommand", "") == []


class TestOptions:
    def test_names(self) -> None:
        values = candidates("version", "-")
        assert "-v" in values
        assert "--nolog" in values

    def test_name_prefix(self) -> None:
        assert candidates("runspider", "--overw") == ["--overwrite-output"]

    def test_suppressed_names(self) -> None:
        assert "--headers" not in candidates("view", "--")

    def test_value(self) -> None:
        assert candidates("version", "-L", "") == [
            "CRITICAL",
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
        ]

    @pytest.mark.parametrize(
        ("words", "expected"),
        [
            # Bash splits ``--loglevel=DE`` into separate words.
            (("--loglevel", "=", "DE"), ["DEBUG"]),
            (("--loglevel", "="), ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]),
            # fish and Zsh keep it as one word, and replace it as one word.
            (("--loglevel=DE",), ["--loglevel=DEBUG"]),
        ],
    )
    def test_value_after_equal_sign(
        self, words: tuple[str, ...], expected: list[str]
    ) -> None:
        assert candidates("version", *words) == expected

    def test_value_without_candidates(self) -> None:
        assert candidates("version", "--logfile", "") == []

    def test_templates(self) -> None:
        assert "crawl" in candidates("genspider", "-t", "")

    def test_settings(self) -> None:
        assert candidates("settings", "--getbool", "COOKIES_EN") == ["COOKIES_ENABLED"]


class TestArguments(TestProjectBase):
    @pytest.fixture
    def spiders_path(self, proj_path: Path) -> Path:
        spiders = proj_path / self.project_name / "spiders"
        for name in ("alpha", "beta"):
            (spiders / f"{name}.py").write_text(
                f"import scrapy\n\n\nclass {name.title()}Spider(scrapy.Spider):\n"
                f"    name = {name!r}\n",
                encoding="utf-8",
            )
        return proj_path

    @pytest.mark.parametrize("command", ["check", "crawl", "edit"])
    def test_spiders(self, command: str, spiders_path: Path) -> None:
        assert candidates(command, "", cwd=spiders_path) == ["alpha", "beta"]

    def test_spiders_prefix(self, spiders_path: Path) -> None:
        assert candidates("crawl", "al", cwd=spiders_path) == ["alpha"]

    def test_spiders_as_option_value(self, spiders_path: Path) -> None:
        assert candidates("parse", "--spider", "b", cwd=spiders_path) == ["beta"]

    def test_spiders_after_options(self, spiders_path: Path) -> None:
        assert candidates("crawl", "-L", "INFO", "", cwd=spiders_path) == [
            "alpha",
            "beta",
        ]

    def test_no_second_spider(self, spiders_path: Path) -> None:
        assert candidates("crawl", "alpha", "", cwd=spiders_path) == []

    def test_outside_project(self) -> None:
        assert candidates("fetch", "--spider", "") == []


class TestCustomCommand(TestProjectBase):
    command_code = """
from collections.abc import Iterable

from scrapy.commands import ScrapyCommand


class Command(ScrapyCommand):
    requires_crawler_process = False

    def short_desc(self):
        return "A custom command"

    def add_options(self, parser):
        super().add_options(parser)
        parser.add_argument("--flavor", choices=["salty", "sweet"])
        parser.add_argument("--color")

    def complete_argument(self, args: list[str]) -> Iterable[str]:
        return ["first", "second"][len(args):]

    def complete_option(self, dest: str) -> Iterable[str]:
        if dest == "color":
            return ["red", "green"]
        return super().complete_option(dest)

    def run(self, args, opts):
        pass
"""

    @pytest.fixture
    def command_path(self, proj_path: Path) -> Path:
        proj_mod_path = proj_path / self.project_name
        commands = proj_mod_path / "commands"
        commands.mkdir()
        (commands / "__init__.py").touch()
        (commands / "custom.py").write_text(self.command_code, encoding="utf-8")
        self._append_settings(
            proj_mod_path, f"COMMANDS_MODULE = '{self.project_name}.commands'\n"
        )
        return proj_path

    def test_name(self, command_path: Path) -> None:
        assert candidates("cust", cwd=command_path) == ["custom"]

    def test_argument(self, command_path: Path) -> None:
        assert candidates("custom", "", cwd=command_path) == ["first", "second"]
        assert candidates("custom", "first", "", cwd=command_path) == ["second"]

    def test_option_choices(self, command_path: Path) -> None:
        assert candidates("custom", "--flavor", "s", cwd=command_path) == [
            "salty",
            "sweet",
        ]

    def test_option(self, command_path: Path) -> None:
        assert candidates("custom", "--color", "", cwd=command_path) == ["red", "green"]
