from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from unittest import mock

import pytest

from scrapy.cmdline import ScrapyArgumentParser
from scrapy.commands.edit import Command
from scrapy.utils.project import get_project_settings
from tests.test_commands import TestProjectBase
from tests.utils.cmdline import call, proc


class TestEditCommand(TestProjectBase):
    """unit testing of the 'scrapy edit' command"""

    @pytest.fixture
    def create_spider(self, proj_path: Path):
        """creates spider needed for tests"""
        # setup: add "cat" as test environment editor
        editor_to_restore = None
        if "EDITOR" in os.environ:
            editor_to_restore = os.environ["EDITOR"]

        os.environ["EDITOR"] = "cat"

        # setup: preserve scrapy settings in local environment
        scrapy_settings_to_restore = None
        if "SCRAPY_SETTINGS_MODULE" in os.environ:
            scrapy_settings_to_restore = os.environ["SCRAPY_SETTINGS_MODULE"]

        # setup: create spider to edit
        test_name = "test_name"
        call("genspider", test_name, "test.com", cwd=proj_path)
        spider = proj_path / self.project_name / "spiders" / "test_name.py"

        try:
            yield proj_path, spider, test_name

        finally:
            # teardown: remove spider from project
            Path.unlink(spider)

            # teardown: restore previous editor
            if editor_to_restore is not None:
                os.environ["EDITOR"] = editor_to_restore
            else:
                # remove editor from os.environ if it exists
                with suppress(KeyError):
                    os.environ.pop("EDITOR")

            # teardown: restore project settings in local environment
            if scrapy_settings_to_restore is not None:
                os.environ["SCRAPY_SETTINGS_MODULE"] = scrapy_settings_to_restore
            else:
                # remove "SCRAPY_SETTINGS_MODULE" from os.environ if it exists
                with suppress(KeyError):
                    os.environ.pop("SCRAPY_SETTINGS_MODULE")

    def test_edit_valid_spider(self, create_spider) -> None:
        """test call to edit command with correct spider name"""
        proj_path, spider, test_name = create_spider
        assert spider.exists()
        assert call("edit", test_name, cwd=proj_path) == 0

    def test_edit_nospider(self, proj_path: Path) -> None:
        """test call to edit if no spider has been specified"""
        assert call("edit", "not_a_valid_spider", cwd=proj_path) == 1

    def test_edit_short_desc(self, proj_path: Path) -> None:
        """Check that short description included in scrapy -h"""
        rtn_code, out, _ = proc("-h", cwd=proj_path)
        assert rtn_code == 0
        cmd = Command()
        assert cmd.short_desc() in out

    def test_edit_command_valid_directory(self, create_spider):
        """calls editor command directly from project directory"""
        proj_path, spider, test_name = create_spider
        failures = []

        # change into cwd
        current = Path.cwd()
        os.chdir(proj_path)

        try:
            # create edit command object
            # teardown required as get_project_settings() mutates os.environ
            cmd = Command()
            cmd.settings = get_project_settings()
            # grabs system editor to mock
            editor = cmd.settings.get("EDITOR")

            # parse commandline arguments
            parser = ScrapyArgumentParser()
            opts, _ = parser.parse_known_args(["edit", test_name])

            with mock.patch(
                "scrapy.commands.edit.os.system", return_value=0
            ) as mock_sys:
                cmd.run([test_name], opts)
                mock_sys.assert_called_once_with(f'{editor} "{spider}"')

        # catch failure so we can restore cwd
        except AssertionError as e:
            failures.append(e)

        finally:
            # restore previous cwd
            os.chdir(current)

            # report test failure
            if failures:
                pytest.fail(f"{failures[0]}")

    def test_edit_as_subprocess(self, create_spider):
        """check that subprocess calls editor"""
        proj_path, _, test_name = create_spider

        spider_text = """
class TestNameSpider(scrapy.Spider):
    name = "test_name"
"""

        _, out, _ = proc("edit", test_name, cwd=proj_path)
        assert spider_text in out

    def test_edit_subprocess_no_project(self, create_spider):
        """check that subprocess does not call editor outside project"""
        proj_path, _, test_name = create_spider

        no_proj = """
The edit command is not available from this location.
These commands are only available from within a project: check, crawl, edit, list, parse.
"""
        _, out, _ = proc("edit", test_name, cwd=proj_path.parent)
        assert no_proj in out
