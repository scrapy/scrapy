from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_commands import TestProjectBase
from tests.utils.cmdline import call, proc


def find_in_file(filename: Path, regex: str) -> re.Match | None:
    """Find first pattern occurrence in file"""
    pattern = re.compile(regex)
    with filename.open("r", encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if match is not None:
                return match
    return None


class TestGenspiderCommand(TestProjectBase):
    def test_arguments(self, proj_path: Path) -> None:
        spider = proj_path / self.project_name / "spiders" / "test_name.py"
        # only pass one argument. spider script shouldn't be created
        assert call("genspider", "test_name", cwd=proj_path) == 2
        assert not spider.exists()
        # pass two arguments <name> <domain>. spider script should be created
        assert call("genspider", "test_name", "test.com", cwd=proj_path) == 0
        assert spider.exists()

    @pytest.mark.parametrize(
        "tplname",
        [
            "basic",
            "crawl",
            "xmlfeed",
            "csvfeed",
        ],
    )
    def test_template(self, tplname: str, proj_path: Path) -> None:
        args = [f"--template={tplname}"] if tplname else []
        spname = "test_spider"
        spmodule = f"{self.project_name}.spiders.{spname}"
        spfile = proj_path / self.project_name / "spiders" / f"{spname}.py"
        _, out, _ = proc("genspider", spname, "test.com", *args, cwd=proj_path)
        assert (
            f"Created spider {spname!r} using template {tplname!r} in module:\n  {spmodule}"
            in out
        )
        assert spfile.exists()
        modify_time_before = spfile.stat().st_mtime
        _, out, _ = proc("genspider", spname, "test.com", *args, cwd=proj_path)
        assert f"Spider {spname!r} already exists in module" in out
        modify_time_after = spfile.stat().st_mtime
        assert modify_time_after == modify_time_before

    def test_list(self, proj_path: Path) -> None:
        assert call("genspider", "--list", cwd=proj_path) == 0

    def test_dump(self, proj_path: Path) -> None:
        assert call("genspider", "--dump=basic", cwd=proj_path) == 0
        assert call("genspider", "-d", "basic", cwd=proj_path) == 0

    def test_same_name_as_project(self, proj_path: Path) -> None:
        assert call("genspider", self.project_name, cwd=proj_path) == 2
        assert not (
            proj_path / self.project_name / "spiders" / f"{self.project_name}.py"
        ).exists()

    @pytest.mark.parametrize("force", [True, False])
    def test_same_filename_as_existing_spider(
        self, force: bool, proj_path: Path
    ) -> None:
        file_name = "example"
        file_path = proj_path / self.project_name / "spiders" / f"{file_name}.py"
        assert call("genspider", file_name, "example.com", cwd=proj_path) == 0
        assert file_path.exists()

        # change name of spider but not its file name
        with file_path.open("r+", encoding="utf-8") as spider_file:
            file_data = spider_file.read()
            file_data = file_data.replace('name = "example"', 'name = "renamed"')
            spider_file.seek(0)
            spider_file.write(file_data)
            spider_file.truncate()
        modify_time_before = file_path.stat().st_mtime
        file_contents_before = file_data

        if force:
            _, out, _ = proc(
                "genspider", "--force", file_name, "example.com", cwd=proj_path
            )
            assert (
                f"Created spider {file_name!r} using template 'basic' in module" in out
            )
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after != modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after != file_contents_before
        else:
            _, out, _ = proc("genspider", file_name, "example.com", cwd=proj_path)
            assert f"{file_path.resolve()} already exists" in out
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after == modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after == file_contents_before

    @pytest.mark.parametrize(
        ("url", "domain"),
        [
            ("test.com", "test.com"),
            ("https://test.com", "test.com"),
        ],
    )
    def test_url(self, url: str, domain: str, proj_path: Path) -> None:
        assert call("genspider", "--force", "test_name", url, cwd=proj_path) == 0
        spider = proj_path / self.project_name / "spiders" / "test_name.py"
        m = find_in_file(spider, r"allowed_domains\s*=\s*\[['\"](.+)['\"]\]")
        assert m is not None
        assert m.group(1) == domain
        m = find_in_file(spider, r"start_urls\s*=\s*\[['\"](.+)['\"]\]")
        assert m is not None
        assert m.group(1) == f"https://{domain}"

    @pytest.mark.parametrize(
        ("url", "expected", "template"),
        [
            # basic
            ("https://test.com", "https://test.com", "basic"),
            ("http://test.com", "http://test.com", "basic"),
            ("http://test.com/other/path", "http://test.com/other/path", "basic"),
            ("test.com/other/path", "https://test.com/other/path", "basic"),
            # crawl
            ("https://test.com", "https://test.com", "crawl"),
            ("http://test.com", "http://test.com", "crawl"),
            ("http://test.com/other/path", "http://test.com/other/path", "crawl"),
            ("test.com/other/path", "https://test.com/other/path", "crawl"),
            ("test.com", "https://test.com", "crawl"),
            # xmlfeed
            ("https://test.com/feed.xml", "https://test.com/feed.xml", "xmlfeed"),
            ("http://test.com/feed.xml", "http://test.com/feed.xml", "xmlfeed"),
            ("test.com/feed.xml", "https://test.com/feed.xml", "xmlfeed"),
            # csvfeed
            ("https://test.com/feed.csv", "https://test.com/feed.csv", "csvfeed"),
            ("http://test.com/feed.xml", "http://test.com/feed.xml", "csvfeed"),
            ("test.com/feed.csv", "https://test.com/feed.csv", "csvfeed"),
        ],
    )
    def test_template_start_urls(
        self, url: str, expected: str, template: str, proj_path: Path
    ) -> None:
        assert (
            call(
                "genspider", "-t", template, "--force", "test_name", url, cwd=proj_path
            )
            == 0
        )
        spider = proj_path / self.project_name / "spiders" / "test_name.py"
        m = find_in_file(spider, r"start_urls\s*=\s*\[['\"](.+)['\"]\]")
        assert m is not None
        assert m.group(1) == expected


class TestGenspiderStandaloneCommand:
    def test_generate_standalone_spider(self, tmp_path: Path) -> None:
        call("genspider", "example", "example.com", cwd=tmp_path)
        assert Path(tmp_path, "example.py").exists()

    @pytest.mark.parametrize("force", [True, False])
    def test_same_name_as_existing_file(self, force: bool, tmp_path: Path) -> None:
        file_name = "example"
        file_path = Path(tmp_path, file_name + ".py")
        _, out, _ = proc("genspider", file_name, "example.com", cwd=tmp_path)
        assert f"Created spider {file_name!r} using template 'basic' " in out
        assert file_path.exists()
        modify_time_before = file_path.stat().st_mtime
        file_contents_before = file_path.read_text(encoding="utf-8")

        if force:
            # use different template to ensure contents were changed
            _, out, _ = proc(
                "genspider",
                "--force",
                "-t",
                "crawl",
                file_name,
                "example.com",
                cwd=tmp_path,
            )
            assert f"Created spider {file_name!r} using template 'crawl' " in out
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after != modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after != file_contents_before
        else:
            _, out, _ = proc("genspider", file_name, "example.com", cwd=tmp_path)
            assert (
                f"{Path(tmp_path, file_name + '.py').resolve()} already exists" in out
            )
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after == modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after == file_contents_before
