from __future__ import annotations

import os
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
        """setup creates spider, teardown removes spider"""
        # setup: create spider to edit
        test_name = "test_name"
        call("genspider", test_name, "test.com", cwd=proj_path)
        spider = proj_path / self.project_name / "spiders" / "test_name.py"
        yield proj_path, spider, test_name
        # teardown: remove spider from project
        Path.unlink(spider)

    def test_edit_valid_spider(self, create_spider) -> None:
        """test call to edit command with correct spider name"""
        proj_path, spider, test_name = create_spider
        assert spider.exists()
        assert call("edit", test_name, cwd=proj_path) == 0

    def test_edit_nospider(self, proj_path: Path) -> None:
        """test call to edit if no spider has been specified"""
        assert call("edit", "not_a_valid_spider", cwd=proj_path) == 1

    def test_edit_implicit(self, create_spider):
        """tests edit command calls editor"""
        proj_path, spider, test_name = create_spider

        # change current working directory
        os.chdir(proj_path)

        # create edit command object
        cmd = Command()
        cmd.settings = get_project_settings()
        editor = cmd.settings.get("EDITOR")

        # parse commandline arguments
        parser = ScrapyArgumentParser()
        opts, _ = parser.parse_known_args(["edit", test_name])

        # mock the operating system
        with mock.patch("scrapy.commands.edit.os.system", return_value=0) as mock_sys:
            cmd.run([test_name], opts)
            mock_sys.assert_called_once_with(f'{editor} "{spider}"')

    def test_edit_help_syntax(self, proj_path: Path) -> None:
        """Check that long description and syntax are included in edit -h"""
        rtn_code, out, _ = proc("edit", "-h", cwd=proj_path)
        assert rtn_code == 0
        cmd = Command()
        assert cmd.long_desc() in out
        assert cmd.syntax() in out

    def test_edit_short_desc(self, proj_path: Path) -> None:
        """Check that short description included in scrapy -h"""
        rtn_code, out, _ = proc("-h", cwd=proj_path)
        assert rtn_code == 0
        cmd = Command()
        assert cmd.short_desc() in out
