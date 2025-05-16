from __future__ import annotations

import argparse
import inspect
import json
import os
import platform
import re
import subprocess
import sys
from contextlib import contextmanager
from io import StringIO
from itertools import chain
from pathlib import Path
from shutil import copytree, rmtree
from stat import S_IWRITE as ANYONE_WRITE_PERMISSION
from tempfile import TemporaryDirectory, TemporaryFile, mkdtemp
from threading import Timer
from typing import TYPE_CHECKING
from unittest import mock, skipIf

import pytest
from twisted.trial import unittest

import scrapy
from scrapy.cmdline import _pop_command_name, _print_unknown_command_msg
from scrapy.commands import ScrapyCommand, ScrapyHelpFormatter, view
from scrapy.commands.startproject import IGNORE
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_testenv
from tests.test_crawler import ExceptionSpider, NoRequestsSpider

if TYPE_CHECKING:
    from collections.abc import Iterator


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


class TestStartprojectCommand(TestProjectBase):
    def test_startproject(self):
        p, out, err = self.proc("startproject", self.project_name)
        print(out)
        print(err, file=sys.stderr)
        assert p.returncode == 0

        assert Path(self.proj_path, "scrapy.cfg").exists()
        assert Path(self.proj_path, "testproject").exists()
        assert Path(self.proj_mod_path, "__init__.py").exists()
        assert Path(self.proj_mod_path, "items.py").exists()
        assert Path(self.proj_mod_path, "pipelines.py").exists()
        assert Path(self.proj_mod_path, "settings.py").exists()
        assert Path(self.proj_mod_path, "spiders", "__init__.py").exists()

        assert self.call("startproject", self.project_name) == 1
        assert self.call("startproject", "wrong---project---name") == 1
        assert self.call("startproject", "sys") == 1

    def test_startproject_with_project_dir(self):
        project_dir = mkdtemp()
        assert self.call("startproject", self.project_name, project_dir) == 0

        assert Path(project_dir, "scrapy.cfg").exists()
        assert Path(project_dir, "testproject").exists()
        assert Path(project_dir, self.project_name, "__init__.py").exists()
        assert Path(project_dir, self.project_name, "items.py").exists()
        assert Path(project_dir, self.project_name, "pipelines.py").exists()
        assert Path(project_dir, self.project_name, "settings.py").exists()
        assert Path(project_dir, self.project_name, "spiders", "__init__.py").exists()

        assert self.call("startproject", self.project_name, project_dir + "2") == 0

        assert self.call("startproject", self.project_name, project_dir) == 1
        assert self.call("startproject", self.project_name + "2", project_dir) == 1
        assert self.call("startproject", "wrong---project---name") == 1
        assert self.call("startproject", "sys") == 1
        assert self.call("startproject") == 2
        assert (
            self.call("startproject", self.project_name, project_dir, "another_params")
            == 2
        )

    def test_existing_project_dir(self):
        project_dir = mkdtemp()
        project_name = self.project_name + "_existing"
        project_path = Path(project_dir, project_name)
        project_path.mkdir()

        p, out, err = self.proc("startproject", project_name, cwd=project_dir)
        print(out)
        print(err, file=sys.stderr)
        assert p.returncode == 0

        assert Path(project_path, "scrapy.cfg").exists()
        assert Path(project_path, project_name).exists()
        assert Path(project_path, project_name, "__init__.py").exists()
        assert Path(project_path, project_name, "items.py").exists()
        assert Path(project_path, project_name, "pipelines.py").exists()
        assert Path(project_path, project_name, "settings.py").exists()
        assert Path(project_path, project_name, "spiders", "__init__.py").exists()


def get_permissions_dict(
    path: str | os.PathLike, renamings=None, ignore=None
) -> dict[str, str]:
    def get_permissions(path: Path) -> str:
        return oct(path.stat().st_mode)

    path_obj = Path(path)

    renamings = renamings or ()
    permissions_dict = {
        ".": get_permissions(path_obj),
    }
    for root, dirs, files in os.walk(path_obj):
        nodes = list(chain(dirs, files))
        if ignore:
            ignored_names = ignore(root, nodes)
            nodes = [node for node in nodes if node not in ignored_names]
        for node in nodes:
            absolute_path = Path(root, node)
            relative_path = str(absolute_path.relative_to(path))
            for search_string, replacement in renamings:
                relative_path = relative_path.replace(search_string, replacement)
            permissions = get_permissions(absolute_path)
            permissions_dict[relative_path] = permissions
    return permissions_dict


class TestStartprojectTemplates(TestProjectBase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.tmpl = str(Path(self.temp_path, "templates"))
        self.tmpl_proj = str(Path(self.tmpl, "project"))

    def test_startproject_template_override(self):
        copytree(Path(scrapy.__path__[0], "templates"), self.tmpl)
        Path(self.tmpl_proj, "root_template").write_bytes(b"")
        assert Path(self.tmpl_proj, "root_template").exists()

        args = ["--set", f"TEMPLATES_DIR={self.tmpl}"]
        p, out, err = self.proc("startproject", self.project_name, *args)
        assert (
            f"New Scrapy project '{self.project_name}', using template directory" in out
        )
        assert self.tmpl_proj in out
        assert Path(self.proj_path, "root_template").exists()

    def test_startproject_permissions_from_writable(self):
        """Check that generated files have the right permissions when the
        template folder has the same permissions as in the project, i.e.
        everything is writable."""
        scrapy_path = scrapy.__path__[0]
        project_template = Path(scrapy_path, "templates", "project")
        project_name = "startproject1"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        destination = mkdtemp()
        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "scrapy.cmdline",
                "startproject",
                project_name,
            ),
            cwd=destination,
            env=self.env,
        )
        process.wait()

        project_dir = Path(destination, project_name)
        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_from_read_only(self):
        """Check that generated files have the right permissions when the
        template folder has been made read-only, which is something that some
        systems do.

        See https://github.com/scrapy/scrapy/pull/4604
        """
        scrapy_path = scrapy.__path__[0]
        templates_dir = Path(scrapy_path, "templates")
        project_template = Path(templates_dir, "project")
        project_name = "startproject2"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        def _make_read_only(path: Path):
            current_permissions = path.stat().st_mode
            path.chmod(current_permissions & ~ANYONE_WRITE_PERMISSION)

        read_only_templates_dir = str(Path(mkdtemp()) / "templates")
        copytree(templates_dir, read_only_templates_dir)

        for root, dirs, files in os.walk(read_only_templates_dir):
            for node in chain(dirs, files):
                _make_read_only(Path(root, node))

        destination = mkdtemp()
        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "scrapy.cmdline",
                "startproject",
                project_name,
                "--set",
                f"TEMPLATES_DIR={read_only_templates_dir}",
            ),
            cwd=destination,
            env=self.env,
        )
        process.wait()

        project_dir = Path(destination, project_name)
        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_unchanged_in_destination(self):
        """Check that preexisting folders and files in the destination folder
        do not see their permissions modified."""
        scrapy_path = scrapy.__path__[0]
        project_template = Path(scrapy_path, "templates", "project")
        project_name = "startproject3"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        destination = mkdtemp()
        project_dir = Path(destination, project_name)

        existing_nodes = {
            oct(permissions)[2:] + extension: permissions
            for extension in ("", ".d")
            for permissions in (
                0o444,
                0o555,
                0o644,
                0o666,
                0o755,
                0o777,
            )
        }
        project_dir.mkdir()
        for node, permissions in existing_nodes.items():
            path = project_dir / node
            if node.endswith(".d"):
                path.mkdir(mode=permissions)
            else:
                path.touch(mode=permissions)
            expected_permissions[node] = oct(path.stat().st_mode)

        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "scrapy.cmdline",
                "startproject",
                project_name,
                ".",
            ),
            cwd=project_dir,
            env=self.env,
        )
        process.wait()

        actual_permissions = get_permissions_dict(project_dir)

        assert actual_permissions == expected_permissions

    def test_startproject_permissions_umask_022(self):
        """Check that generated files have the right permissions when the
        system uses a umask value that causes new files to have different
        permissions than those from the template folder."""

        @contextmanager
        def umask(new_mask):
            cur_mask = os.umask(new_mask)
            yield
            os.umask(cur_mask)

        scrapy_path = scrapy.__path__[0]
        project_template = Path(scrapy_path, "templates", "project")
        project_name = "umaskproject"
        renamings = (
            ("module", project_name),
            (".tmpl", ""),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        with umask(0o002):
            destination = mkdtemp()
            process = subprocess.Popen(
                (
                    sys.executable,
                    "-m",
                    "scrapy.cmdline",
                    "startproject",
                    project_name,
                ),
                cwd=destination,
                env=self.env,
            )
            process.wait()

            project_dir = Path(destination, project_name)
            actual_permissions = get_permissions_dict(project_dir)

            assert actual_permissions == expected_permissions


class TestCommandBase(TestProjectBase):
    def setUp(self):
        super().setUp()
        self.call("startproject", self.project_name)
        self.cwd = Path(self.temp_path, self.project_name)
        self.env["SCRAPY_SETTINGS_MODULE"] = f"{self.project_name}.settings"


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


class TestRunSpiderCommand(TestCommandBase):
    spider_filename = "myspider.py"

    debug_log_spider = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug("It Works!")
        return
        yield
"""

    badspider = """
import scrapy

class BadSpider(scrapy.Spider):
    name = "bad"
    async def start(self):
        raise Exception("oops!")
        yield
        """

    @contextmanager
    def _create_file(self, content: str, name: str | None = None) -> Iterator[str]:
        with TemporaryDirectory() as tmpdir:
            if name:
                fname = Path(tmpdir, name).resolve()
            else:
                fname = Path(tmpdir, self.spider_filename).resolve()
            fname.write_text(content, encoding="utf-8")
            yield str(fname)

    def runspider(self, code, name=None, args=()):
        with self._create_file(code, name) as fname:
            return self.proc("runspider", fname, *args)

    def get_log(self, code, name=None, args=()):
        p, stdout, stderr = self.runspider(code, name, args=args)
        return stderr

    def test_runspider(self):
        log = self.get_log(self.debug_log_spider)
        assert "DEBUG: It Works!" in log
        assert "INFO: Spider opened" in log
        assert "INFO: Closing spider (finished)" in log
        assert "INFO: Spider closed (finished)" in log

    def test_run_fail_spider(self):
        proc, _, _ = self.runspider(
            "import scrapy\n" + inspect.getsource(ExceptionSpider)
        )
        ret = proc.returncode
        assert ret != 0

    def test_run_good_spider(self):
        proc, _, _ = self.runspider(
            "import scrapy\n" + inspect.getsource(NoRequestsSpider)
        )
        ret = proc.returncode
        assert ret == 0

    def test_runspider_log_level(self):
        log = self.get_log(self.debug_log_spider, args=("-s", "LOG_LEVEL=INFO"))
        assert "DEBUG: It Works!" not in log
        assert "INFO: Spider opened" in log

    def test_runspider_dnscache_disabled(self):
        # see https://github.com/scrapy/scrapy/issues/2811
        # The spider below should not be able to connect to localhost:12345,
        # which is intended,
        # but this should not be because of DNS lookup error
        # assumption: localhost will resolve in all cases (true?)
        dnscache_spider = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'
    start_urls = ['http://localhost:12345']

    def parse(self, response):
        return {'test': 'value'}
"""
        log = self.get_log(dnscache_spider, args=("-s", "DNSCACHE_ENABLED=False"))
        assert "DNSLookupError" not in log
        assert "INFO: Spider opened" in log

    def test_runspider_log_short_names(self):
        log1 = self.get_log(self.debug_log_spider, args=("-s", "LOG_SHORT_NAMES=1"))
        assert "[myspider] DEBUG: It Works!" in log1
        assert "[scrapy]" in log1
        assert "[scrapy.core.engine]" not in log1

        log2 = self.get_log(self.debug_log_spider, args=("-s", "LOG_SHORT_NAMES=0"))
        assert "[myspider] DEBUG: It Works!" in log2
        assert "[scrapy]" not in log2
        assert "[scrapy.core.engine]" in log2

    def test_runspider_no_spider_found(self):
        log = self.get_log("from scrapy.spiders import Spider\n")
        assert "No spider found in file" in log

    def test_runspider_file_not_found(self):
        _, _, log = self.proc("runspider", "some_non_existent_file")
        assert "File not found: some_non_existent_file" in log

    def test_runspider_unable_to_load(self):
        log = self.get_log("", name="myspider.txt")
        assert "Unable to load" in log

    def test_start_errors(self):
        log = self.get_log(self.badspider, name="badspider.py")
        assert "start" in log
        assert "badspider.py" in log, log

    def test_asyncio_enabled_true(self):
        log = self.get_log(
            self.debug_log_spider,
            args=[
                "-s",
                "TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            ],
        )
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_asyncio_enabled_default(self):
        log = self.get_log(self.debug_log_spider, args=[])
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_asyncio_enabled_false(self):
        log = self.get_log(
            self.debug_log_spider,
            args=["-s", "TWISTED_REACTOR=twisted.internet.selectreactor.SelectReactor"],
        )
        assert "Using reactor: twisted.internet.selectreactor.SelectReactor" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            not in log
        )

    @pytest.mark.requires_uvloop
    def test_custom_asyncio_loop_enabled_true(self):
        log = self.get_log(
            self.debug_log_spider,
            args=[
                "-s",
                "TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "-s",
                "ASYNCIO_EVENT_LOOP=uvloop.Loop",
            ],
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    def test_custom_asyncio_loop_enabled_false(self):
        log = self.get_log(
            self.debug_log_spider,
            args=[
                "-s",
                "TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            ],
        )
        import asyncio

        if sys.platform != "win32":
            loop = asyncio.new_event_loop()
        else:
            loop = asyncio.SelectorEventLoop()
        assert (
            f"Using asyncio event loop: {loop.__module__}.{loop.__class__.__name__}"
            in log
        )

    def test_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug('FEEDS: {}'.format(self.settings.getdict('FEEDS')))
        return
        yield
"""
        args = ["-o", "example.json"]
        log = self.get_log(spider_code, args=args)
        assert "[myspider] DEBUG: FEEDS: {'example.json': {'format': 'json'}}" in log

    def test_overwrite_output(self):
        spider_code = """
import json
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug(
            'FEEDS: {}'.format(
                json.dumps(self.settings.getdict('FEEDS'), sort_keys=True)
            )
        )
        return
        yield
"""
        Path(self.cwd, "example.json").write_text("not empty", encoding="utf-8")
        args = ["-O", "example.json"]
        log = self.get_log(spider_code, args=args)
        assert (
            '[myspider] DEBUG: FEEDS: {"example.json": {"format": "json", "overwrite": true}}'
            in log
        )
        with Path(self.cwd, "example.json").open(encoding="utf-8") as f2:
            first_line = f2.readline()
        assert first_line != "not empty"

    def test_output_and_overwrite_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        return
        yield
"""
        args = ["-o", "example1.json", "-O", "example2.json"]
        log = self.get_log(spider_code, args=args)
        assert (
            "error: Please use only one of -o/--output and -O/--overwrite-output" in log
        )

    def test_output_stdout(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug('FEEDS: {}'.format(self.settings.getdict('FEEDS')))
        return
        yield
"""
        args = ["-o", "-:json"]
        log = self.get_log(spider_code, args=args)
        assert "[myspider] DEBUG: FEEDS: {'stdout:': {'format': 'json'}}" in log

    @skipIf(platform.system() == "Windows", reason="Linux only")
    def test_absolute_path_linux(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    start_urls = ["data:,"]

    def parse(self, response):
        yield {"hello": "world"}
        """
        temp_dir = mkdtemp()

        args = ["-o", f"{temp_dir}/output1.json:json"]
        log = self.get_log(spider_code, args=args)
        assert (
            f"[scrapy.extensions.feedexport] INFO: Stored json feed (1 items) in: {temp_dir}/output1.json"
            in log
        )

        args = ["-o", f"{temp_dir}/output2.json"]
        log = self.get_log(spider_code, args=args)
        assert (
            f"[scrapy.extensions.feedexport] INFO: Stored json feed (1 items) in: {temp_dir}/output2.json"
            in log
        )

    @skipIf(platform.system() != "Windows", reason="Windows only")
    def test_absolute_path_windows(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    start_urls = ["data:,"]

    def parse(self, response):
        yield {"hello": "world"}
        """
        temp_dir = mkdtemp()

        args = ["-o", f"{temp_dir}\\output1.json:json"]
        log = self.get_log(spider_code, args=args)
        assert (
            f"[scrapy.extensions.feedexport] INFO: Stored json feed (1 items) in: {temp_dir}\\output1.json"
            in log
        )

        args = ["-o", f"{temp_dir}\\output2.json"]
        log = self.get_log(spider_code, args=args)
        assert (
            f"[scrapy.extensions.feedexport] INFO: Stored json feed (1 items) in: {temp_dir}\\output2.json"
            in log
        )

    def test_args_change_settings(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.settings.set("FOO", kwargs.get("foo"))
        return spider

    async def start(self):
        self.logger.info(f"The value of FOO is {self.settings.getint('FOO')}")
        return
        yield
"""
        args = ["-a", "foo=42"]
        log = self.get_log(spider_code, args=args)
        assert "Spider closed (finished)" in log
        assert "The value of FOO is 42" in log


class TestWindowsRunSpiderCommand(TestRunSpiderCommand):
    spider_filename = "myspider.pyw"

    def setUp(self):
        if platform.system() != "Windows":
            raise unittest.SkipTest("Windows required for .pyw files")
        return super().setUp()

    def test_start_errors(self):
        log = self.get_log(self.badspider, name="badspider.pyw")
        assert "start" in log
        assert "badspider.pyw" in log

    def test_runspider_unable_to_load(self):
        raise unittest.SkipTest("Already Tested in 'RunSpiderCommandTest' ")


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


class TestCrawlCommand(TestCommandBase):
    def crawl(self, code, args=()):
        Path(self.proj_mod_path, "spiders", "myspider.py").write_text(
            code, encoding="utf-8"
        )
        return self.proc("crawl", "myspider", *args)

    def get_log(self, code, args=()):
        _, _, stderr = self.crawl(code, args=args)
        return stderr

    def test_no_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug('It works!')
        return
        yield
"""
        log = self.get_log(spider_code)
        assert "[myspider] DEBUG: It works!" in log

    def test_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug('FEEDS: {}'.format(self.settings.getdict('FEEDS')))
        return
        yield
"""
        args = ["-o", "example.json"]
        log = self.get_log(spider_code, args=args)
        assert "[myspider] DEBUG: FEEDS: {'example.json': {'format': 'json'}}" in log

    def test_overwrite_output(self):
        spider_code = """
import json
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug(
            'FEEDS: {}'.format(
                json.dumps(self.settings.getdict('FEEDS'), sort_keys=True)
            )
        )
        return
        yield
"""
        Path(self.cwd, "example.json").write_text("not empty", encoding="utf-8")
        args = ["-O", "example.json"]
        log = self.get_log(spider_code, args=args)
        assert (
            '[myspider] DEBUG: FEEDS: {"example.json": {"format": "json", "overwrite": true}}'
            in log
        )
        with Path(self.cwd, "example.json").open(encoding="utf-8") as f2:
            first_line = f2.readline()
        assert first_line != "not empty"

    def test_output_and_overwrite_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        return
        yield
"""
        args = ["-o", "example1.json", "-O", "example2.json"]
        log = self.get_log(spider_code, args=args)
        assert (
            "error: Please use only one of -o/--output and -O/--overwrite-output" in log
        )


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
