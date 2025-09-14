from __future__ import annotations

import asyncio
import inspect
import platform
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from typing import TYPE_CHECKING

import pytest

from tests.test_commands import TestCommandBase
from tests.test_crawler import ExceptionSpider, NoRequestsSpider

if TYPE_CHECKING:
    from collections.abc import Iterator


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
        _, _, stderr = self.runspider(code, name, args=args)
        return stderr

    def test_runspider(self):
        log = self.get_log(self.debug_log_spider)
        assert "DEBUG: It Works!" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
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

    def test_runspider_default_reactor(self):
        log = self.get_log(self.debug_log_spider, args=("-s", "TWISTED_REACTOR="))
        assert "DEBUG: It Works!" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            not in log
        )
        assert "INFO: Spider opened" in log
        assert "INFO: Closing spider (finished)" in log
        assert "INFO: Spider closed (finished)" in log

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

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "RETRY_ENABLED": False,
    }

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

    @pytest.mark.skipif(platform.system() == "Windows", reason="Linux only")
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

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows only")
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


@pytest.mark.skipif(
    platform.system() != "Windows", reason="Windows required for .pyw files"
)
class TestWindowsRunSpiderCommand(TestRunSpiderCommand):
    spider_filename = "myspider.pyw"

    def test_start_errors(self):
        log = self.get_log(self.badspider, name="badspider.pyw")
        assert "start" in log
        assert "badspider.pyw" in log

    def test_runspider_unable_to_load(self):
        pytest.skip("Already Tested in 'RunSpiderCommandTest'")
