from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.http import Response, TextResponse
from scrapy.linkextractors import LinkExtractor

if TYPE_CHECKING:
    import argparse
    from collections.abc import AsyncIterator


class Command(ScrapyCommand):
    default_settings = {
        "LOG_LEVEL": "INFO",
        "LOGSTATS_INTERVAL": 1,
        "CLOSESPIDER_TIMEOUT": 10,
    }

    def short_desc(self) -> str:
        return "Run quick benchmark test"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        with _BenchServer():
            assert self.crawler_process
            self.crawler_process.crawl(_BenchSpider, total=100000)
            self.crawler_process.start()


class _BenchServer:
    def __enter__(self) -> None:
        from scrapy.utils.test import get_testenv

        pargs = [sys.executable, "-u", "-m", "scrapy.utils.benchserver"]
        self.proc = subprocess.Popen(  # noqa: S603
            pargs, stdout=subprocess.PIPE, env=get_testenv()
        )
        assert self.proc.stdout
        self.proc.stdout.readline()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)


class _BenchSpider(scrapy.Spider):
    """A spider that follows all links"""

    name = "follow"
    total = 10000
    show = 20
    baseurl = "http://localhost:8998"
    link_extractor = LinkExtractor()

    async def start(self) -> AsyncIterator[Any]:
        qargs = {"total": self.total, "show": self.show}
        url = f"{self.baseurl}?{urlencode(qargs, doseq=True)}"
        yield scrapy.Request(url, dont_filter=True)

    def parse(self, response: Response) -> Any:
        assert isinstance(response, TextResponse)
        for link in self.link_extractor.extract_links(response):
            yield scrapy.Request(link.url, callback=self.parse)
