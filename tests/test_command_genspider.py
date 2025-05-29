from __future__ import annotations

import os
from pathlib import Path

from tests.test_commands import TestCommandBase, TestProjectBase


class TestGenspiderCommand(TestCommandBase):
    def test_arguments(self):
        # only pass one argument. spider script shouldn't be created
        assert self.call("genspider", "test_name") == 2
        assert not Path(self.proj_mod_path, "spiders", "test_name.py").exists()
        # pass two arguments <name> <domain>. spider script should be created
        assert self.call("genspider", "test_name", "test.com") == 0
        assert Path(self.proj_mod_path, "spiders", "test_name.py").exists()

    def test_template(self, tplname="crawl"):
        args = [f"--template={tplname}"] if tplname else []
        spname = "test_spider"
        spmodule = f"{self.project_name}.spiders.{spname}"
        p, out, err = self.proc("genspider", spname, "test.com", *args)
        assert (
            f"Created spider {spname!r} using template {tplname!r} in module:{os.linesep}  {spmodule}"
            in out
        )
        assert Path(self.proj_mod_path, "spiders", "test_spider.py").exists()
        modify_time_before = (
            Path(self.proj_mod_path, "spiders", "test_spider.py").stat().st_mtime
        )
        p, out, err = self.proc("genspider", spname, "test.com", *args)
        assert f"Spider {spname!r} already exists in module" in out
        modify_time_after = (
            Path(self.proj_mod_path, "spiders", "test_spider.py").stat().st_mtime
        )
        assert modify_time_after == modify_time_before

    def test_template_basic(self):
        self.test_template("basic")

    def test_template_csvfeed(self):
        self.test_template("csvfeed")

    def test_template_xmlfeed(self):
        self.test_template("xmlfeed")

    def test_list(self):
        assert self.call("genspider", "--list") == 0

    def test_dump(self):
        assert self.call("genspider", "--dump=basic") == 0
        assert self.call("genspider", "-d", "basic") == 0

    def test_same_name_as_project(self):
        assert self.call("genspider", self.project_name) == 2
        assert not Path(
            self.proj_mod_path, "spiders", f"{self.project_name}.py"
        ).exists()

    def test_same_filename_as_existing_spider(self, force=False):
        file_name = "example"
        file_path = Path(self.proj_mod_path, "spiders", f"{file_name}.py")
        assert self.call("genspider", file_name, "example.com") == 0
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
            p, out, err = self.proc("genspider", "--force", file_name, "example.com")
            assert (
                f"Created spider {file_name!r} using template 'basic' in module" in out
            )
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after != modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after != file_contents_before
        else:
            p, out, err = self.proc("genspider", file_name, "example.com")
            assert f"{file_path.resolve()} already exists" in out
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after == modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after == file_contents_before

    def test_same_filename_as_existing_spider_force(self):
        self.test_same_filename_as_existing_spider(force=True)

    def test_url(self, url="test.com", domain="test.com"):
        assert self.call("genspider", "--force", "test_name", url) == 0
        assert (
            self.find_in_file(
                Path(self.proj_mod_path, "spiders", "test_name.py"),
                r"allowed_domains\s*=\s*\[['\"](.+)['\"]\]",
            ).group(1)
            == domain
        )
        assert (
            self.find_in_file(
                Path(self.proj_mod_path, "spiders", "test_name.py"),
                r"start_urls\s*=\s*\[['\"](.+)['\"]\]",
            ).group(1)
            == f"https://{domain}"
        )

    def test_url_schema(self):
        self.test_url("https://test.com", "test.com")

    def test_template_start_urls(
        self, url="test.com", expected="https://test.com", template="basic"
    ):
        assert self.call("genspider", "-t", template, "--force", "test_name", url) == 0
        assert (
            self.find_in_file(
                Path(self.proj_mod_path, "spiders", "test_name.py"),
                r"start_urls\s*=\s*\[['\"](.+)['\"]\]",
            ).group(1)
            == expected
        )

    def test_genspider_basic_start_urls(self):
        self.test_template_start_urls("https://test.com", "https://test.com", "basic")
        self.test_template_start_urls("http://test.com", "http://test.com", "basic")
        self.test_template_start_urls(
            "http://test.com/other/path", "http://test.com/other/path", "basic"
        )
        self.test_template_start_urls(
            "test.com/other/path", "https://test.com/other/path", "basic"
        )

    def test_genspider_crawl_start_urls(self):
        self.test_template_start_urls("https://test.com", "https://test.com", "crawl")
        self.test_template_start_urls("http://test.com", "http://test.com", "crawl")
        self.test_template_start_urls(
            "http://test.com/other/path", "http://test.com/other/path", "crawl"
        )
        self.test_template_start_urls(
            "test.com/other/path", "https://test.com/other/path", "crawl"
        )
        self.test_template_start_urls("test.com", "https://test.com", "crawl")

    def test_genspider_xmlfeed_start_urls(self):
        self.test_template_start_urls(
            "https://test.com/feed.xml", "https://test.com/feed.xml", "xmlfeed"
        )
        self.test_template_start_urls(
            "http://test.com/feed.xml", "http://test.com/feed.xml", "xmlfeed"
        )
        self.test_template_start_urls(
            "test.com/feed.xml", "https://test.com/feed.xml", "xmlfeed"
        )

    def test_genspider_csvfeed_start_urls(self):
        self.test_template_start_urls(
            "https://test.com/feed.csv", "https://test.com/feed.csv", "csvfeed"
        )
        self.test_template_start_urls(
            "http://test.com/feed.xml", "http://test.com/feed.xml", "csvfeed"
        )
        self.test_template_start_urls(
            "test.com/feed.csv", "https://test.com/feed.csv", "csvfeed"
        )


class TestGenspiderStandaloneCommand(TestProjectBase):
    def test_generate_standalone_spider(self):
        self.call("genspider", "example", "example.com")
        assert Path(self.temp_path, "example.py").exists()

    def test_same_name_as_existing_file(self, force=False):
        file_name = "example"
        file_path = Path(self.temp_path, file_name + ".py")
        p, out, err = self.proc("genspider", file_name, "example.com")
        assert f"Created spider {file_name!r} using template 'basic' " in out
        assert file_path.exists()
        modify_time_before = file_path.stat().st_mtime
        file_contents_before = file_path.read_text(encoding="utf-8")

        if force:
            # use different template to ensure contents were changed
            p, out, err = self.proc(
                "genspider", "--force", "-t", "crawl", file_name, "example.com"
            )
            assert f"Created spider {file_name!r} using template 'crawl' " in out
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after != modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after != file_contents_before
        else:
            p, out, err = self.proc("genspider", file_name, "example.com")
            assert (
                f"{Path(self.temp_path, file_name + '.py').resolve()} already exists"
                in out
            )
            modify_time_after = file_path.stat().st_mtime
            assert modify_time_after == modify_time_before
            file_contents_after = file_path.read_text(encoding="utf-8")
            assert file_contents_after == file_contents_before

    def test_same_name_as_existing_file_force(self):
        self.test_same_name_as_existing_file(force=True)
