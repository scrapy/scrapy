from __future__ import annotations

import asyncio
import inspect
import platform
import sys
from typing import TYPE_CHECKING

import pytest

from tests.test_crawler import ExceptionSpider, NoRequestsSpider
from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class TestRunSpiderCommand:
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

    def runspider(
        self, cwd: Path, code: str, name: str | None = None, args: Iterable[str] = ()
    ) -> tuple[int, str, str]:
        fname = cwd / (name or self.spider_filename)
        fname.write_text(code, encoding="utf-8")
        return proc("runspider", str(fname), *args, cwd=cwd)

    def get_log(
        self, cwd: Path, code: str, name: str | None = None, args: Iterable[str] = ()
    ) -> str:
        _, _, stderr = self.runspider(cwd, code, name, args=args)
        return stderr

    def test_runspider(self, tmp_path: Path) -> None:
        log = self.get_log(tmp_path, self.debug_log_spider)
        assert "DEBUG: It Works!" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "INFO: Spider closed (finished)" in log

    def test_run_fail_spider(self, tmp_path: Path) -> None:
        ret, _, _ = self.runspider(
            tmp_path, "import scrapy\n" + inspect.getsource(ExceptionSpider)
        )
        assert ret != 0

    def test_run_good_spider(self, tmp_path: Path) -> None:
        ret, _, _ = self.runspider(
            tmp_path, "import scrapy\n" + inspect.getsource(NoRequestsSpider)
        )
        assert ret == 0

    def test_runspider_log_level(self, tmp_path: Path) -> None:
        log = self.get_log(
            tmp_path, self.debug_log_spider, args=("-s", "LOG_LEVEL=INFO")
        )
        assert "DEBUG: It Works!" not in log
        assert "INFO: Spider opened" in log

    def test_runspider_default_reactor(self, tmp_path: Path) -> None:
        log = self.get_log(
            tmp_path, self.debug_log_spider, args=("-s", "TWISTED_REACTOR=")
        )
        assert "DEBUG: It Works!" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            not in log
        )
        assert "INFO: Spider opened" in log
        assert "INFO: Closing spider (finished)" in log
        assert "INFO: Spider closed (finished)" in log

    def test_runspider_dnscache_disabled(self, tmp_path: Path) -> None:
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

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "RETRY_ENABLED": False,
    }

    def parse(self, response):
        return {'test': 'value'}
"""
        log = self.get_log(
            tmp_path, dnscache_spider, args=("-s", "DNSCACHE_ENABLED=False")
        )
        assert "DNSLookupError" not in log
        assert "INFO: Spider opened" in log

    @pytest.mark.parametrize("value", [False, True])
    def test_runspider_log_short_names(self, tmp_path: Path, value: bool) -> None:
        log1 = self.get_log(
            tmp_path, self.debug_log_spider, args=("-s", f"LOG_SHORT_NAMES={value}")
        )
        assert "[myspider] DEBUG: It Works!" in log1
        assert ("[scrapy]" in log1) is value
        assert ("[scrapy.core.engine]" in log1) is not value

    def test_runspider_no_spider_found(self, tmp_path: Path) -> None:
        log = self.get_log(tmp_path, "from scrapy.spiders import Spider\n")
        assert "No spider found in file" in log

    def test_runspider_file_not_found(self) -> None:
        _, _, log = proc("runspider", "some_non_existent_file")
        assert "File not found: some_non_existent_file" in log

    def test_runspider_unable_to_load(self, tmp_path: Path) -> None:
        log = self.get_log(tmp_path, "", name="myspider.txt")
        assert "Unable to load" in log

    def test_start_errors(self, tmp_path: Path) -> None:
        log = self.get_log(tmp_path, self.badspider, name="badspider.py")
        assert "start" in log
        assert "badspider.py" in log, log

    def test_asyncio_enabled_true(self, tmp_path: Path) -> None:
        log = self.get_log(
            tmp_path,
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

    def test_asyncio_enabled_default(self, tmp_path: Path) -> None:
        log = self.get_log(tmp_path, self.debug_log_spider)
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_asyncio_enabled_false(self, tmp_path: Path) -> None:
        log = self.get_log(
            tmp_path,
            self.debug_log_spider,
            args=["-s", "TWISTED_REACTOR=twisted.internet.selectreactor.SelectReactor"],
        )
        assert "Using reactor: twisted.internet.selectreactor.SelectReactor" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            not in log
        )

    @pytest.mark.requires_uvloop
    def test_custom_asyncio_loop_enabled_true(self, tmp_path: Path) -> None:
        log = self.get_log(
            tmp_path,
            self.debug_log_spider,
            args=[
                "-s",
                "TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "-s",
                "ASYNCIO_EVENT_LOOP=uvloop.Loop",
            ],
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    def test_custom_asyncio_loop_enabled_false(self, tmp_path: Path) -> None:
        log = self.get_log(
            tmp_path,
            self.debug_log_spider,
            args=[
                "-s",
                "TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            ],
        )
        if sys.platform != "win32":
            loop = asyncio.new_event_loop()
        else:
            loop = asyncio.SelectorEventLoop()
        assert (
            f"Using asyncio event loop: {loop.__module__}.{loop.__class__.__name__}"
            in log
        )

    def test_output(self, tmp_path: Path) -> None:
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
        log = self.get_log(tmp_path, spider_code, args=args)
        assert "[myspider] DEBUG: FEEDS: {'example.json': {'format': 'json'}}" in log

    def test_overwrite_output(self, tmp_path: Path) -> None:
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
        (tmp_path / "example.json").write_text("not empty", encoding="utf-8")
        args = ["-O", "example.json"]
        log = self.get_log(tmp_path, spider_code, args=args)
        assert (
            '[myspider] DEBUG: FEEDS: {"example.json": {"format": "json", "overwrite": true}}'
            in log
        )
        with (tmp_path / "example.json").open(encoding="utf-8") as f2:
            first_line = f2.readline()
        assert first_line != "not empty"

    def test_output_and_overwrite_output(self, tmp_path: Path) -> None:
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        return
        yield
"""
        args = ["-o", "example1.json", "-O", "example2.json"]
        log = self.get_log(tmp_path, spider_code, args=args)
        assert (
            "error: Please use only one of -o/--output and -O/--overwrite-output" in log
        )

    def test_output_stdout(self, tmp_path: Path) -> None:
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
        log = self.get_log(tmp_path, spider_code, args=args)
        assert "[myspider] DEBUG: FEEDS: {'stdout:': {'format': 'json'}}" in log

    @pytest.mark.parametrize("arg", ["output.json:json", "output.json"])
    def test_absolute_path(self, tmp_path: Path, arg: str) -> None:
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    start_urls = ["data:,"]

    def parse(self, response):
        yield {"hello": "world"}
        """

        args = ["-o", str(tmp_path / arg)]
        log = self.get_log(tmp_path, spider_code, args=args)
        assert (
            f"[scrapy.extensions.feedexport] INFO: Stored json feed (1 items) in: {tmp_path / 'output.json'}"
            in log
        )

    def test_args_change_settings(self, tmp_path: Path) -> None:
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
        log = self.get_log(tmp_path, spider_code, args=args)
        assert "Spider closed (finished)" in log
        assert "The value of FOO is 42" in log


@pytest.mark.skipif(
    platform.system() != "Windows", reason="Windows required for .pyw files"
)
class TestWindowsRunSpiderCommand(TestRunSpiderCommand):
    spider_filename = "myspider.pyw"

    def test_start_errors(self, tmp_path: Path) -> None:
        log = self.get_log(tmp_path, self.badspider, name="badspider.pyw")
        assert "start" in log
        assert "badspider.pyw" in log

    def test_runspider_unable_to_load(self, tmp_path: Path) -> None:
        pytest.skip("Already Tested in 'RunSpiderCommandTest'")
