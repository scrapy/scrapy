from __future__ import annotations

from pathlib import Path

from tests.test_commands import TestCommandBase


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
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Spider closed (finished)" in log

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

    def test_default_reactor(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    async def start(self):
        self.logger.debug('It works!')
        return
        yield
"""
        log = self.get_log(spider_code, args=("-s", "TWISTED_REACTOR="))
        assert "[myspider] DEBUG: It works!" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            not in log
        )
        assert "Spider closed (finished)" in log
