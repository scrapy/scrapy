"""Scrapy Shell

See documentation in docs/topics/shell.rst

"""

from __future__ import annotations

import contextlib
import os
import signal
from typing import TYPE_CHECKING, Any

from itemadapter import is_item
from twisted.internet import threads
from twisted.internet.defer import Deferred
from twisted.python import threadable
from w3lib.url import any_to_uri

import scrapy
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.conf import get_config
from scrapy.utils.console import DEFAULT_PYTHON_SHELLS, start_python_console
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.defer import _schedule_coro, deferred_f_from_coro_f
from scrapy.utils.misc import load_object
from scrapy.utils.reactor import is_asyncio_reactor_installed, set_asyncio_event_loop
from scrapy.utils.response import open_in_browser

if TYPE_CHECKING:
    from collections.abc import Callable

# Hopefully temporary architecture notes
#
# The Shell class is always instantiated in the "main" thread. There are two
# official ways to use it:
# 1. scrapy.commands.shell, which makes a secondary thread and calls
# CrawlerProcess.start() in it, which runs a reactor there.
# 2. scrapy.shell.inspect_response(), which just creates Shell() in the current
# thread.
#
# Shell.inthread is True when this class is run in a thread separate from the
# reactor, e.g. the 1st way (in other words, the reactor is in a secondary
# thread).
# Shell.inthread is False when this class is run in the same thread as the
# reactor, e.g. the 2nd way.
# The only thing that differs is availability of fetch() (it needs the
# reactor to be in a separate thread: the shell sends the request to
# the reactor and waits for the result synchronously).
#
# Thus the only thing Shell needs an event loop for is fetch(). More machinery
# is used for it to work. In chronological order:
# 1. scrapy.commands.shell.Command.run() creates a crawler and an engine, then
# calls
# _schedule_coro(crawler.engine.start_async(_start_request_processing=False)).
# (_schedule_coro() here is problematic for reactorless becaused it calls
# is_asyncio_available() and the loop is not running yet), which initializes
# the engine but doesn't start processing of the start requests (which we don't
# have anyway).
# 2. scrapy.commands.shell.Command.run() calls crawler_process.start() in a
# thread which starts a reactor in that thread.
# 3. When fetch() is called, it prepares a request and calls Shell._schedule()
# in the reactor thread (via threads.blockingCallFromThread()).
# 4. Shell._schedule() calls Shell._open_spider() (on the first call).
# 5. Shell._open_spider() calls engine.open_spider_async(close_if_idle=False)
# and engine._start_request_processing().
# 6. Shell._schedule() calls engine.crawl(request), scheduling the request.
# 7. Shell._schedule() via _request_deferred() waits until the request callback
# is called. When it's called, the response becomes available.


class Shell:
    relevant_classes: tuple[type, ...] = (Crawler, Spider, Request, Response, Settings)

    def __init__(
        self,
        crawler: Crawler,
        update_vars: Callable[[dict[str, Any]], None] | None = None,
        code: str | None = None,
    ):
        self.crawler: Crawler = crawler
        self.update_vars: Callable[[dict[str, Any]], None] = update_vars or (
            lambda x: None
        )
        self.item_class: type = load_object(crawler.settings["DEFAULT_ITEM_CLASS"])
        self.spider: Spider | None = None
        self.inthread: bool = not threadable.isInIOThread()
        self.code: str | None = code
        self.vars: dict[str, Any] = {}

    def start(
        self,
        url: str | None = None,
        request: Request | None = None,
        response: Response | None = None,
        spider: Spider | None = None,
        redirect: bool = True,
    ) -> None:
        # disable accidental Ctrl-C key press from shutting down the engine
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if url:
            self.fetch(url, spider, redirect=redirect)
        elif request:
            self.fetch(request, spider)
        elif response:
            request = response.request
            self.populate_vars(response, request, spider)
        else:
            self.populate_vars()
        if self.code:
            print(eval(self.code, globals(), self.vars))  # noqa: S307
        else:
            # Detect interactive shell setting in scrapy.cfg
            # e.g.: ~/.config/scrapy.cfg or ~/.scrapy.cfg
            # [settings]
            # # shell can be one of ipython, bpython or python;
            # # to be used as the interactive python console, if available.
            # # (default is ipython, fallbacks in the order listed above)
            # shell = python
            cfg = get_config()
            section, option = "settings", "shell"
            env = os.environ.get("SCRAPY_PYTHON_SHELL")
            shells = []
            if env:
                shells += env.strip().lower().split(",")
            elif cfg.has_option(section, option):
                shells += [cfg.get(section, option).strip().lower()]
            else:  # try all by default
                shells += DEFAULT_PYTHON_SHELLS.keys()
            # always add standard shell as fallback
            shells += ["python"]
            start_python_console(
                self.vars, shells=shells, banner=self.vars.pop("banner", "")
            )

    def _schedule(self, request: Request, spider: Spider | None) -> Deferred[Any]:
        if is_asyncio_reactor_installed():
            # set the asyncio event loop for the current thread
            event_loop_path = self.crawler.settings["ASYNCIO_EVENT_LOOP"]
            set_asyncio_event_loop(event_loop_path)

        def crawl_request(_: None) -> None:
            assert self.crawler.engine is not None
            self.crawler.engine.crawl(request)

        d2 = self._open_spider(request, spider)
        d2.addCallback(crawl_request)

        d = _request_deferred(request)
        d.addCallback(lambda x: (x, spider))
        return d

    @deferred_f_from_coro_f
    async def _open_spider(self, request: Request, spider: Spider | None) -> None:
        if self.spider:
            return

        if spider is None:
            spider = self.crawler.spider or self.crawler._create_spider()

        self.crawler.spider = spider
        assert self.crawler.engine
        await self.crawler.engine.open_spider_async(close_if_idle=False)
        _schedule_coro(self.crawler.engine._start_request_processing())
        self.spider = spider

    def fetch(
        self,
        request_or_url: Request | str,
        spider: Spider | None = None,
        redirect: bool = True,
        **kwargs: Any,
    ) -> None:
        from twisted.internet import reactor

        if isinstance(request_or_url, Request):
            request = request_or_url
        else:
            url = any_to_uri(request_or_url)
            request = Request(url, dont_filter=True, **kwargs)
            if redirect:
                request.meta["handle_httpstatus_list"] = SequenceExclude(
                    range(300, 400)
                )
            else:
                request.meta["handle_httpstatus_all"] = True
        response = None
        with contextlib.suppress(IgnoreRequest):
            response, spider = threads.blockingCallFromThread(
                reactor, self._schedule, request, spider
            )
        self.populate_vars(response, request, spider)

    def populate_vars(
        self,
        response: Response | None = None,
        request: Request | None = None,
        spider: Spider | None = None,
    ) -> None:
        self.vars["scrapy"] = scrapy
        self.vars["crawler"] = self.crawler
        self.vars["item"] = self.item_class()
        self.vars["settings"] = self.crawler.settings
        self.vars["spider"] = spider
        self.vars["request"] = request
        self.vars["response"] = response
        if self.inthread:
            self.vars["fetch"] = self.fetch
        self.vars["view"] = open_in_browser
        self.vars["shelp"] = self.print_help
        self.update_vars(self.vars)
        if not self.code:
            self.vars["banner"] = self.get_help()

    def print_help(self) -> None:
        print(self.get_help())

    def get_help(self) -> str:
        b = []
        b.append("Available Scrapy objects:")
        b.append(
            "  scrapy     scrapy module (contains scrapy.Request, scrapy.Selector, etc)"
        )
        for k, v in sorted(self.vars.items()):
            if self._is_relevant(v):
                b.append(f"  {k:<10} {v}")
        b.append("Useful shortcuts:")
        if self.inthread:
            b.append(
                "  fetch(url[, redirect=True]) "
                "Fetch URL and update local objects (by default, redirects are followed)"
            )
            b.append(
                "  fetch(req)                  "
                "Fetch a scrapy.Request and update local objects "
            )
        b.append("  shelp()           Shell help (print this help)")
        b.append("  view(response)    View response in a browser")

        return "\n".join(f"[s] {line}" for line in b) + "\n"

    def _is_relevant(self, value: Any) -> bool:
        return isinstance(value, self.relevant_classes) or is_item(value)


def inspect_response(response: Response, spider: Spider) -> None:
    """Open a shell to inspect the given response"""
    # Shell.start removes the SIGINT handler, so save it and re-add it after
    # the shell has closed
    sigint_handler = signal.getsignal(signal.SIGINT)
    Shell(spider.crawler).start(response=response, spider=spider)
    signal.signal(signal.SIGINT, sigint_handler)


def _request_deferred(request: Request) -> Deferred[Any]:
    """Wrap a request inside a Deferred.

    This function is harmful, do not use it until you know what you are doing.

    This returns a Deferred whose first pair of callbacks are the request
    callback and errback. The Deferred also triggers when the request
    callback/errback is executed (i.e. when the request is downloaded)

    WARNING: Do not call request.replace() until after the deferred is called.
    """
    request_callback = request.callback
    request_errback = request.errback

    def _restore_callbacks(result: Any) -> Any:
        request.callback = request_callback
        request.errback = request_errback
        return result

    d: Deferred[Any] = Deferred()
    d.addBoth(_restore_callbacks)
    if request.callback:
        d.addCallback(request.callback)
    if request.errback:
        d.addErrback(request.errback)

    request.callback, request.errback = d.callback, d.errback
    return d
