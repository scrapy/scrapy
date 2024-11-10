from __future__ import annotations

import argparse
import subprocess  # nosec
import sys
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.http import Response, TextResponse
from scrapy.linkextractors import LinkExtractor

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy import Request


class Command(ScrapyCommand):
    """Run a quick benchmark test by initiating a crawler process."""
    default_settings = {
        "LOG_LEVEL": "INFO",
        "LOGSTATS_INTERVAL": 1,
        "CLOSESPIDER_TIMEOUT": 10,
    }

    def short_desc(self) -> str:
        """Return a brief description of the command."""
        return "Run quick benchmark test"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """Execute the benchmark test with specified arguments and options.
        
        Args:
            args (list[str]): Command-line arguments for the command.
            opts (argparse.Namespace): Parsed command-line options.
        """
        with _BenchServer():
            assert self.crawler_process
            self.crawler_process.crawl(_BenchSpider, total=100000)
            self.crawler_process.start()


class _BenchServer:
    """Context manager for starting and stopping a benchmark server subprocess."""
    def __enter__(self) -> None:
        """Start the benchmark server as a subprocess."""
        from scrapy.utils.test import get_testenv

        pargs = [sys.executable, "-u", "-m", "scrapy.utils.benchserver"]
        self.proc = subprocess.Popen(
            pargs, stdout=subprocess.PIPE, env=get_testenv()
        )  # nosec
        assert self.proc.stdout
        self.proc.stdout.readline()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Terminate the benchmark server subprocess and wait for it to finish."""
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)


class _BenchSpider(scrapy.Spider):
    """Spider that follows all links on a given page and extracts further links."""

    name = "follow"
    total = 10000
    show = 20
    baseurl = "http://localhost:8998"
    link_extractor = LinkExtractor()

    def start_requests(self) -> Iterable[Request]:
        """Generate the initial request to start crawling from the base URL.
        
        Returns:
            Iterable[Request]: A list containing the initial request.
        """
        qargs = {"total": self.total, "show": self.show}
        url = f"{self.baseurl}?{urlencode(qargs, doseq=True)}"
        return [scrapy.Request(url, dont_filter=True)]

    def parse(self, response: Response) -> Any:
        """Parse the response and yield requests for all extracted links.
        
        Args:
            response (Response): The response object to parse.
        
        Yields:
            Request: A new request for each extracted link found.
        """
        assert isinstance(response, TextResponse)
        for link in self.link_extractor.extract_links(response):
            yield scrapy.Request(link.url, callback=self.parse)