"""Scrapy Shell

See documentation in docs/topics/shell.rst

"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import warnings
from typing import TYPE_CHECKING, Any

from itemadapter import is_item
from twisted.internet import threads
from twisted.python import threadable
from w3lib.url import any_to_uri

import scrapy
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils._shell import DEFAULT_PYTHON_SHELLS, start_python_console
from scrapy.utils.conf import get_config
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.misc import load_object
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
# Shell._inthread is True when this class is run in a thread separate from the
# reactor, e.g. the 1st way (in other words, the reactor is in a secondary
# thread).
# Shell._inthread is False when this class is run in the same thread as the
# reactor, e.g. the 2nd way.
# The only thing that differs is availability of fetch() (it needs the
# reactor to be in a separate thread: the shell sends the request to
# the reactor and waits for the result synchronously).
#
# Thus the only thing Shell needs an event loop for is fetch(). The engine is
# never started as the shell doesn't need request processing and
# download_async() still works.
# In chronological order:
# 1. scrapy.commands.shell.Command.run() creates a crawler and an engine.
# 2. scrapy.commands.shell.Command.run() calls crawler_process.start() in a
# thread which starts a reactor in that thread.
# 3. When fetch() is called, it prepares a request and calls Shell._schedule()
# in the reactor thread (via threads.blockingCallFromThread()).
# 4. Shell._schedule() calls Shell._open_spider() (on the first call).
# 5. Shell._open_spider() calls
# engine.open_spider_async(close_if_idle=False).
# 6. Shell._schedule() calls engine.download_async(request), which completes
# with the response.
#
# In the reactorless mode this is slightly different, the engine creation
# happens in the event loop thread as many things need either a reactor or a
# running event loop.
#
# Other architecture problems:
# * scrapy.cmdline.execute() creates an AsyncCrawlerProcess instance which
#   immediately installs a reactor (which is maybe not thread-specific?) or an
#   event loop (which *is* thread-specific, so the main thread will always have
#   a (not running) loop installed.
# * The shell uses several private members of Crawler (_create_engine(),
#   _create_spider()) and of AsyncCrawlerProcess (_reactorless_loop).


class Shell:
    relevant_classes: tuple[type, ...] = (Crawler, Spider, Request, Response, Settings)

    def __init__(
        self,
        crawler: Crawler,
        update_vars: Callable[[dict[str, Any]], None] | None = None,
        code: str | None = None,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        self._use_reactor = crawler.settings.getbool("TWISTED_REACTOR_ENABLED")
        if not self._use_reactor and not loop:  # pragma: no cover
            raise RuntimeError(
                "Shell needs the crawler loop reference when TWISTED_REACTOR_ENABLED=False."
            )
        self._loop = loop
        self.crawler: Crawler = crawler
        self.update_vars: Callable[[dict[str, Any]], None] = update_vars or (
            lambda x: None
        )
        self.item_class: type = load_object(crawler.settings["DEFAULT_ITEM_CLASS"])
        self.spider: Spider | None = None
        if self._use_reactor:
            self._inthread: bool = not threadable.isInIOThread()
        else:
            try:
                # in case there is also a running loop in the main thread
                current_loop = asyncio.get_running_loop()
                self._inthread = current_loop is not self._loop
            except RuntimeError:
                self._inthread = True
        self.code: str | None = code
        self.vars: dict[str, Any] = {}

    @property
    def inthread(self) -> bool:  # pragma: no cover
        warnings.warn(
            "Shell.inthread is deprecated, use Shell.fetch_available instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self._inthread

    @property
    def fetch_available(self) -> bool:
        """Whether fetch() can be used."""
        return self._inthread

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
            # Detect interactive shell setting in pyproject.toml
            # [tool.scrapy.settings]
            # # shell can be one of ipython, bpython or python;
            # # to be used as the interactive python console, if available.
            # # (default is ipython, fallbacks in the order listed above)
            # shell = "python"
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

    async def _schedule(self, request: Request, spider: Spider | None) -> Response:
        """Download the request through the engine and return the response.

        Runs in the reactor thread when using the reactor, or in the asyncio
        event loop thread otherwise.
        """
        if not self.spider:
            await self._open_spider(spider)
        return await self.crawler.engine.download_async(request)

    async def _open_spider(self, spider: Spider | None) -> None:
        if spider is None:
            spider = self.crawler.spider or self.crawler._create_spider()

        self.crawler.spider = spider
        await self.crawler.engine.open_spider_async(close_if_idle=False)
        self.spider = spider

    def fetch(
        self,
        request_or_url: Request | str,
        spider: Spider | None = None,
        redirect: bool = True,
        **kwargs: Any,
    ) -> None:
        if isinstance(request_or_url, Request):
            request = request_or_url
            if (
                not (request.callback is None or request.callback is NO_CALLBACK)
                or request.errback
            ):
                warnings.warn(
                    "Callbacks and errbacks of Request objects passed to fetch() are ignored.",
                    stacklevel=2,
                )
        else:
            url = any_to_uri(request_or_url)
            request = Request(url, callback=NO_CALLBACK, dont_filter=True, **kwargs)
            if not redirect:
                request.meta["dont_redirect"] = True
        response: Response | None = None
        if self._use_reactor:
            from twisted.internet import reactor

            with contextlib.suppress(IgnoreRequest):
                response = threads.blockingCallFromThread(
                    reactor,
                    deferred_f_from_coro_f(self._schedule),  # type: ignore[arg-type]
                    request,
                    spider,
                )
        else:
            assert self._loop
            with contextlib.suppress(IgnoreRequest):
                future = asyncio.run_coroutine_threadsafe(
                    self._schedule(request, spider), self._loop
                )
                response = future.result()
        self.populate_vars(response, request, self.spider)

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
        if self.fetch_available:
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
        if self.fetch_available:
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

    def _is_relevant(self, value: object) -> bool:
        return isinstance(value, self.relevant_classes) or is_item(value)


def inspect_response(response: Response, spider: Spider) -> None:
    """Open a shell to inspect the given response"""
    # Shell.start removes the SIGINT handler, so save it and re-add it after
    # the shell has closed
    sigint_handler = signal.getsignal(signal.SIGINT)
    if not spider.crawler.settings.getbool("TWISTED_REACTOR_ENABLED"):
        loop = asyncio.get_running_loop()
    else:
        loop = None
    Shell(spider.crawler, loop=loop).start(response=response, spider=spider)
    signal.signal(signal.SIGINT, sigint_handler)
