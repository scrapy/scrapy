from __future__ import annotations

import sys
from argparse import Namespace  # noqa: TC003
from typing import TYPE_CHECKING

from w3lib.url import is_url

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.http import Request, Response
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.spider import DefaultSpider, spidercls_for_request

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from scrapy import Spider


class Command(ScrapyCommand):
    requires_project = False

    def syntax(self) -> str:
        return "[options] <url>"

    def short_desc(self) -> str:
        return "Fetch a URL using the Scrapy downloader"

    def long_desc(self) -> str:
        return (
            "Fetch a URL using the Scrapy downloader and print its content"
            " to stdout. You may want to use --nolog to disable logging"
        )

    def add_options(self, parser: ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument("--spider", dest="spider", help="use this spider")
        parser.add_argument(
            "--headers",
            dest="headers",
            action="store_true",
            help="print response HTTP headers instead of body",
        )
        parser.add_argument(
            "--no-redirect",
            dest="no_redirect",
            action="store_true",
            default=False,
            help="do not handle HTTP 3xx status codes and print response as-is",
        )

    def _print_headers(self, headers: dict[bytes, list[bytes]], prefix: bytes) -> None:
        for key, values in headers.items():
            for value in values:
                self._print_bytes(prefix + b" " + key + b": " + value)

    def _print_response(self, response: Response, opts: Namespace) -> None:
        if opts.headers:
            assert response.request
            self._print_headers(response.request.headers, b">")
            print(">")
            self._print_headers(response.headers, b"<")
        else:
            self._print_bytes(response.body)

    def _print_bytes(self, bytes_: bytes) -> None:
        sys.stdout.buffer.write(bytes_ + b"\n")

    def run(self, args: list[str], opts: Namespace) -> None:
        if len(args) != 1 or not is_url(args[0]):
            raise UsageError
        request = Request(
            args[0],
            callback=self._print_response,
            cb_kwargs={"opts": opts},
            dont_filter=True,
        )
        # by default, let the framework handle redirects,
        # i.e. command handles all codes expect 3xx
        if not opts.no_redirect:
            request.meta["handle_httpstatus_list"] = SequenceExclude(range(300, 400))
        else:
            request.meta["handle_httpstatus_all"] = True

        spidercls: type[Spider] = DefaultSpider
        assert self.crawler_process
        spider_loader = self.crawler_process.spider_loader
        if opts.spider:
            spidercls = spider_loader.load(opts.spider)
        else:
            spidercls = spidercls_for_request(spider_loader, request, spidercls)

        async def start(self):
            yield request

        spidercls.start = start  # type: ignore[method-assign,attr-defined]

        self.crawler_process.crawl(spidercls)
        self.crawler_process.start()
