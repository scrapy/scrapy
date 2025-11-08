from __future__ import annotations

from typing import TYPE_CHECKING

from tests.test_commands import TestProjectBase
from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class TestCrawlCommand(TestProjectBase):
    def crawl(
        self, code: str, proj_path: Path, args: Iterable[str] = ()
    ) -> tuple[int, str, str]:
        (proj_path / self.project_name / "spiders" / "myspider.py").write_text(
            code, encoding="utf-8"
        )
        return proc("crawl", "myspider", *args, cwd=proj_path)

    def get_log(self, code: str, proj_path: Path, args: Iterable[str] = ()) -> str:
        _, _, stderr = self.crawl(code, proj_path, args=args)
        return stderr

    def test_no_output(self, proj_path: Path) -> None:
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug('It works!')
        return
        yield
"""
        log = self.get_log(spider_code, proj_path)
        assert "[myspider] DEBUG: It works!" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Spider closed (finished)" in log

    def test_output(self, proj_path: Path) -> None:
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
        log = self.get_log(spider_code, proj_path, args=args)
        assert "[myspider] DEBUG: FEEDS: {'example.json': {'format': 'json'}}" in log

    def test_overwrite_output(self, proj_path: Path) -> None:
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
        j = proj_path / "example.json"
        j.write_text("not empty", encoding="utf-8")
        args = ["-O", "example.json"]
        log = self.get_log(spider_code, proj_path, args=args)
        assert (
            '[myspider] DEBUG: FEEDS: {"example.json": {"format": "json", "overwrite": true}}'
            in log
        )
        with j.open(encoding="utf-8") as f2:
            first_line = f2.readline()
        assert first_line != "not empty"

    def test_output_and_overwrite_output(self, proj_path: Path) -> None:
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        return
        yield
"""
        args = ["-o", "example1.json", "-O", "example2.json"]
        log = self.get_log(spider_code, proj_path, args=args)
        assert (
            "error: Please use only one of -o/--output and -O/--overwrite-output" in log
        )

    def test_default_reactor(self, proj_path: Path) -> None:
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug('It works!')
        return
        yield
"""
        log = self.get_log(spider_code, proj_path, args=("-s", "TWISTED_REACTOR="))
        assert "[myspider] DEBUG: It works!" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            not in log
        )
        assert "Spider closed (finished)" in log
