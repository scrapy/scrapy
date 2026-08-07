"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

from __future__ import annotations

import asyncio
from threading import Thread
from typing import TYPE_CHECKING, Any, ClassVar

from scrapy.commands import ScrapyCommand
from scrapy.crawler import AsyncCrawlerProcess, Crawler
from scrapy.http import Request
from scrapy.shell import Shell
from scrapy.utils.defer import _schedule_coro
from scrapy.utils.spider import DefaultSpider, spidercls_for_request
from scrapy.utils.url import guess_scheme

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

    from scrapy import Spider


class Command(ScrapyCommand):
    default_settings: ClassVar[dict[str, Any]] = {
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

    def update_vars(self, vars: dict[str, Any]) -> None:  # noqa: A002
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
        loop: asyncio.AbstractEventLoop | None = None
        if crawler.settings.getbool("TWISTED_REACTOR_ENABLED"):
            self._init_with_reactor(crawler)
        else:
            self._init_without_reactor(crawler)
            loop = self._get_reactorless_loop()
        shell = Shell(crawler, update_vars=self.update_vars, code=opts.code, loop=loop)
        shell.start(url=url, redirect=not opts.no_redirect)

    def _init_with_reactor(self, crawler: Crawler) -> None:
        # Create the engine and run start_async() in the main thread
        crawler.engine = crawler._create_engine()
        _schedule_coro(crawler.engine.start_async(_start_request_processing=False))
        self._start_crawler_thread()

    def _init_without_reactor(self, crawler: Crawler) -> None:
        # Create the engine and run start_async() in the event loop thread
        loop = self._get_reactorless_loop()
        self._start_crawler_thread()

        async def _init_engine() -> None:
            # We may need to wait until some parts of start_async() have
            # finished, which may need a special event in the engine and may
            # wait until https://github.com/scrapy/scrapy/issues/6916
            crawler.engine = crawler._create_engine()
            loop.create_task(
                crawler.engine.start_async(_start_request_processing=False)
            )

        future = asyncio.run_coroutine_threadsafe(_init_engine(), loop)
        future.result()

    def _get_reactorless_loop(self) -> asyncio.AbstractEventLoop:
        assert self.crawler_process
        assert isinstance(self.crawler_process, AsyncCrawlerProcess)
        loop = self.crawler_process._reactorless_loop
        assert loop
        return loop

    def _start_crawler_thread(self) -> None:
        """Run self.crawler_process.start() in a separate thread."""
        assert self.crawler_process
        t = Thread(
            target=self.crawler_process.start,
            kwargs={"stop_after_crawl": False, "install_signal_handlers": False},
        )
        t.daemon = True
        t.start()
