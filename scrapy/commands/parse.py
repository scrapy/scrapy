from __future__ import annotations

import argparse
import functools
import inspect
import json
import logging
from typing import TYPE_CHECKING, Any, TypeVar, overload

from itemadapter import ItemAdapter, is_item
from twisted.internet.defer import Deferred, maybeDeferred
from w3lib.url import is_url

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError
from scrapy.http import Request, Response
from scrapy.utils import display
from scrapy.utils.asyncgen import collect_asyncgen
from scrapy.utils.defer import aiter_errback, deferred_from_coro
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.spider import spidercls_for_request

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Iterable

    from twisted.python.failure import Failure

    from scrapy.http.request import CallbackT
    from scrapy.spiders import Spider


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class Command(BaseRunSpiderCommand):
    requires_project = True

    spider: Spider | None = None
    items: dict[int, list[Any]] = {}
    requests: dict[int, list[Request]] = {}
    spidercls: type[Spider] | None

    first_response = None

    def syntax(self) -> str:
        return "[options] <url>"

    def short_desc(self) -> str:
        return "Parse URL (using its spider) and print the results"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "--spider",
            dest="spider",
            default=None,
            help="use this spider without looking for one",
        )
        parser.add_argument(
            "--pipelines", action="store_true", help="process items through pipelines"
        )
        parser.add_argument(
            "--nolinks",
            dest="nolinks",
            action="store_true",
            help="don't show links to follow (extracted requests)",
        )
        parser.add_argument(
            "--noitems",
            dest="noitems",
            action="store_true",
            help="don't show scraped items",
        )
        parser.add_argument(
            "--nocolour",
            dest="nocolour",
            action="store_true",
            help="avoid using pygments to colorize the output",
        )
        parser.add_argument(
            "-r",
            "--rules",
            dest="rules",
            action="store_true",
            help="use CrawlSpider rules to discover the callback",
        )
        parser.add_argument(
            "-c",
            "--callback",
            dest="callback",
            help="use this callback for parsing, instead looking for a callback",
        )
        parser.add_argument(
            "-m",
            "--meta",
            dest="meta",
            help="inject extra meta into the Request, it must be a valid raw json string",
        )
        parser.add_argument(
            "--cbkwargs",
            dest="cbkwargs",
            help="inject extra callback kwargs into the Request, it must be a valid raw json string",
        )
        parser.add_argument(
            "-d",
            "--depth",
            dest="depth",
            type=int,
            default=1,
            help="maximum depth for parsing requests [default: %(default)s]",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            dest="verbose",
            action="store_true",
            help="print each depth level one by one",
        )

    @property
    def max_level(self) -> int:
        max_items, max_requests = 0, 0
        if self.items:
            max_items = max(self.items)
        if self.requests:
            max_requests = max(self.requests)
        return max(max_items, max_requests)

    def handle_exception(self, _failure: Failure) -> None:
        logger.error(
            "An error is caught while iterating the async iterable",
            exc_info=failure_to_exc_info(_failure),
        )

    @overload
    def iterate_spider_output(
        self, result: AsyncGenerator[_T] | Coroutine[Any, Any, _T]
    ) -> Deferred[_T]: ...

    @overload
    def iterate_spider_output(self, result: _T) -> Iterable[Any]: ...

    def iterate_spider_output(self, result: Any) -> Iterable[Any] | Deferred[Any]:
        if inspect.isasyncgen(result):
            d = deferred_from_coro(
                collect_asyncgen(aiter_errback(result, self.handle_exception))
            )
            d.addCallback(self.iterate_spider_output)
            return d
        if inspect.iscoroutine(result):
            d = deferred_from_coro(result)
            d.addCallback(self.iterate_spider_output)
            return d
        return arg_to_iter(deferred_from_coro(result))

    def add_items(self, lvl: int, new_items: list[Any]) -> None:
        old_items = self.items.get(lvl, [])
        self.items[lvl] = old_items + new_items

    def add_requests(self, lvl: int, new_reqs: list[Request]) -> None:
        old_reqs = self.requests.get(lvl, [])
        self.requests[lvl] = old_reqs + new_reqs

    def print_items(self, lvl: int | None = None, colour: bool = True) -> None:
        if lvl is None:
            items = [item for lst in self.items.values() for item in lst]
        else:
            items = self.items.get(lvl, [])

        print("# Scraped Items ", "-" * 60)
        display.pprint([ItemAdapter(x).asdict() for x in items], colorize=colour)

    def print_requests(self, lvl: int | None = None, colour: bool = True) -> None:
        if lvl is None:
            if self.requests:
                requests = self.requests[max(self.requests)]
            else:
                requests = []
        else:
            requests = self.requests.get(lvl, [])

        print("# Requests ", "-" * 65)
        display.pprint(requests, colorize=colour)

    def print_results(self, opts: argparse.Namespace) -> None:
        colour = not opts.nocolour

        if opts.verbose:
            for level in range(1, self.max_level + 1):
                print(f"\n>>> DEPTH LEVEL: {level} <<<")
                if not opts.noitems:
                    self.print_items(level, colour)
                if not opts.nolinks:
                    self.print_requests(level, colour)
        else:
            print(f"\n>>> STATUS DEPTH LEVEL {self.max_level} <<<")
            if not opts.noitems:
                self.print_items(colour=colour)
            if not opts.nolinks:
                self.print_requests(colour=colour)

    def _get_items_and_requests(
        self,
        spider_output: Iterable[Any],
        opts: argparse.Namespace,
        depth: int,
        spider: Spider,
        callback: CallbackT,
    ) -> tuple[list[Any], list[Request], argparse.Namespace, int, Spider, CallbackT]:
        items, requests = [], []
        for x in spider_output:
            if is_item(x):
                items.append(x)
            elif isinstance(x, Request):
                requests.append(x)
        return items, requests, opts, depth, spider, callback

    def run_callback(
        self,
        response: Response,
        callback: CallbackT,
        cb_kwargs: dict[str, Any] | None = None,
    ) -> Deferred[Any]:
        cb_kwargs = cb_kwargs or {}
        d = maybeDeferred(self.iterate_spider_output, callback(response, **cb_kwargs))
        return d

    def get_callback_from_rules(
        self, spider: Spider, response: Response
    ) -> CallbackT | str | None:
        if getattr(spider, "rules", None):
            for rule in spider.rules:  # type: ignore[attr-defined]
                if rule.link_extractor.matches(response.url):
                    return rule.callback or "parse"
        else:
            logger.error(
                "No CrawlSpider rules found in spider %(spider)r, "
                "please specify a callback to use for parsing",
                {"spider": spider.name},
            )
        return None

    def set_spidercls(self, url: str, opts: argparse.Namespace) -> None:
        assert self.crawler_process
        spider_loader = self.crawler_process.spider_loader
        if opts.spider:
            try:
                self.spidercls = spider_loader.load(opts.spider)
            except KeyError:
                logger.error(
                    "Unable to find spider: %(spider)s", {"spider": opts.spider}
                )
        else:
            self.spidercls = spidercls_for_request(spider_loader, Request(url))
            if not self.spidercls:
                logger.error("Unable to find spider for: %(url)s", {"url": url})

        def _start_requests(spider: Spider) -> Iterable[Request]:
            yield self.prepare_request(spider, Request(url), opts)

        if self.spidercls:
            self.spidercls.start_requests = _start_requests  # type: ignore[assignment,method-assign]

    def start_parsing(self, url: str, opts: argparse.Namespace) -> None:
        assert self.crawler_process
        assert self.spidercls
        self.crawler_process.crawl(self.spidercls, **opts.spargs)
        self.pcrawler = list(self.crawler_process.crawlers)[0]
        self.crawler_process.start()

        if not self.first_response:
            logger.error("No response downloaded for: %(url)s", {"url": url})

    def scraped_data(
        self,
        args: tuple[
            list[Any], list[Request], argparse.Namespace, int, Spider, CallbackT
        ],
    ) -> list[Any]:
        items, requests, opts, depth, spider, callback = args
        if opts.pipelines:
            itemproc = self.pcrawler.engine.scraper.itemproc
            for item in items:
                itemproc.process_item(item, spider)
        self.add_items(depth, items)
        self.add_requests(depth, requests)

        scraped_data = items if opts.output else []
        if depth < opts.depth:
            for req in requests:
                req.meta["_depth"] = depth + 1
                req.meta["_callback"] = req.callback
                req.callback = callback
            scraped_data += requests

        return scraped_data

    def _get_callback(
        self,
        *,
        spider: Spider,
        opts: argparse.Namespace,
        response: Response | None = None,
    ) -> CallbackT:
        cb: str | CallbackT | None = None
        if response:
            cb = response.meta["_callback"]
        if not cb:
            if opts.callback:
                cb = opts.callback
            elif response and opts.rules and self.first_response == response:
                cb = self.get_callback_from_rules(spider, response)
                if not cb:
                    raise ValueError(
                        f"Cannot find a rule that matches {response.url!r} in spider: "
                        f"{spider.name}"
                    )
            else:
                cb = "parse"

        if not callable(cb):
            assert cb is not None
            cb_method = getattr(spider, cb, None)
            if callable(cb_method):
                cb = cb_method
            else:
                raise ValueError(
                    f"Cannot find callback {cb!r} in spider: {spider.name}"
                )
        assert callable(cb)
        return cb

    def prepare_request(
        self, spider: Spider, request: Request, opts: argparse.Namespace
    ) -> Request:
        def callback(response: Response, **cb_kwargs: Any) -> Deferred[list[Any]]:
            # memorize first request
            if not self.first_response:
                self.first_response = response

            cb = self._get_callback(spider=spider, opts=opts, response=response)

            # parse items and requests
            depth: int = response.meta["_depth"]

            d = self.run_callback(response, cb, cb_kwargs)
            d.addCallback(self._get_items_and_requests, opts, depth, spider, callback)
            d.addCallback(self.scraped_data)
            return d

        # update request meta if any extra meta was passed through the --meta/-m opts.
        if opts.meta:
            request.meta.update(opts.meta)

        # update cb_kwargs if any extra values were was passed through the --cbkwargs option.
        if opts.cbkwargs:
            request.cb_kwargs.update(opts.cbkwargs)

        request.meta["_depth"] = 1
        request.meta["_callback"] = request.callback
        if not request.callback and not opts.rules:
            cb = self._get_callback(spider=spider, opts=opts)
            functools.update_wrapper(callback, cb)
        request.callback = callback
        return request

    def process_options(self, args: list[str], opts: argparse.Namespace) -> None:
        super().process_options(args, opts)

        self.process_request_meta(opts)
        self.process_request_cb_kwargs(opts)

    def process_request_meta(self, opts: argparse.Namespace) -> None:
        if opts.meta:
            try:
                opts.meta = json.loads(opts.meta)
            except ValueError:
                raise UsageError(
                    "Invalid -m/--meta value, pass a valid json string to -m or --meta. "
                    'Example: --meta=\'{"foo" : "bar"}\'',
                    print_help=False,
                )

    def process_request_cb_kwargs(self, opts: argparse.Namespace) -> None:
        if opts.cbkwargs:
            try:
                opts.cbkwargs = json.loads(opts.cbkwargs)
            except ValueError:
                raise UsageError(
                    "Invalid --cbkwargs value, pass a valid json string to --cbkwargs. "
                    'Example: --cbkwargs=\'{"foo" : "bar"}\'',
                    print_help=False,
                )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        # parse arguments
        if not len(args) == 1 or not is_url(args[0]):
            raise UsageError()
        url = args[0]

        # prepare spidercls
        self.set_spidercls(url, opts)

        if self.spidercls and opts.depth > 0:
            self.start_parsing(url, opts)
            self.print_results(opts)
