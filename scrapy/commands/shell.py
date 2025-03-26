"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

from __future__ import annotations

from threading import Thread
from typing import TYPE_CHECKING, Any

from scrapy.commands import ScrapyCommand
from scrapy.http import Request
from scrapy.shell import Shell
from scrapy.utils.spider import DefaultSpider, spidercls_for_request
from scrapy.utils.url import guess_scheme

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

    from scrapy import Spider


class Command(ScrapyCommand):
    requires_project = False
    default_settings = {
        "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        "KEEP_ALIVE": True,
        "LOGSTATS_INTERVAL": 0,
    }

    def syntax(self) -> str:
        return "[url|file]"

    def short_desc(self) -> str:
        return "Interactive scraping console"

    def long_desc(self) -> str:
        return (
            "Interactive console for scraping the given url or file. "
            "Use ./file.html syntax or full path for local file."
        )

    def add_options(self, parser: ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "-c",
            dest="code",
            help="evaluate the code in the shell, print the result and exit",
        )
        parser.add_argument("--spider", dest="spider", help="use this spider")
        parser.add_argument(
            "--no-redirect",
            dest="no_redirect",
            action="store_true",
            default=False,
            help="do not handle HTTP 3xx status codes and print response as-is",
        )

    def update_vars(self, vars: dict[str, Any]) -> None:
        """You can use this function to update the Scrapy objects that will be
        available in the shell
        """

    def run(self, args: list[str], opts: Namespace) -> None:
        url = args[0] if args else None
        if url:
            # first argument may be a local file
            url = guess_scheme(url)

        assert self.crawler_process
        spider_loader = self.crawler_process.spider_loader

        spidercls: type[Spider] = DefaultSpider
        if opts.spider:
            spidercls = spider_loader.load(opts.spider)
        elif url:
            spidercls = spidercls_for_request(
                spider_loader, Request(url), spidercls, log_multiple=True
            )

        # The crawler is created this way since the Shell manually handles the
        # crawling engine, so the set up in the crawl method won't work
        crawler = self.crawler_process._create_crawler(spidercls)
        crawler._apply_settings()
        # The Shell class needs a persistent engine in the crawler
        crawler.engine = crawler._create_engine()
        crawler.engine.start(_start_request_processing=False)

        self._start_crawler_thread()

        shell = Shell(crawler, update_vars=self.update_vars, code=opts.code)
        shell.start(url=url, redirect=not opts.no_redirect)

    def _start_crawler_thread(self) -> None:
        assert self.crawler_process
        t = Thread(
            target=self.crawler_process.start,
            kwargs={"stop_after_crawl": False, "install_signal_handlers": False},
        )
        t.daemon = True
        t.start()
