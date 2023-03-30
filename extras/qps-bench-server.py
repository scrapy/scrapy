import os
import signal

from itemadapter import is_item
from twisted.internet import defer, threads
from twisted.python import threadable
from w3lib.url import any_to_uri

from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.conf import get_config
from scrapy.utils.console import DEFAULT_PYTHON_SHELLS, start_python_console
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.misc import load_object
from scrapy.utils.reactor import (
    is_asyncio_reactor_installed,
    set_asyncio_event_loop
)
from scrapy.utils.response import open_in_browser


class ScrapyShell:
    objects = (
        Crawler,
        Spider,
        Request,
        Response,
        Settings,
    )

    def __init__(self, crawler, update_vars=None, code=None):
        self.crawler = crawler
        self.update_vars = update_vars or (lambda x: None)
        self.item_class = load_object(crawler.settings["DEFAULT_ITEM_CLASS"])
        self.spider = None
        self.in_thread = not threadable.isInIOThread()
        self.code = code
        self.vars = {}

    def start(self, url=None, request=None, response=None, spider=None, redirect=True):
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # ignore SIGINT signal
        self.fetch(url, spider, redirect=redirect) if url else (
            self.fetch(request, spider) if request
            else (self.populate_vars(response, request, spider), self.execute_code())
        )

    def _schedule(self, request, spider):
        if is_asyncio_reactor_installed():
            set_asyncio_event_loop(self.crawler.settings["ASYNCIO_EVENT_LOOP"])
        spider = self._open_spider(request, spider)
        d = _request_deferred(request)
        d.addCallback(lambda x: (x, spider))
        self.crawler.engine.crawl(request)
        return d

    def fetch(self, request_or_url, spider=None, redirect=True, **kwargs):
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
        try:
            response, spider = threads.blockingCallFromThread(
                reactor, self._schedule, request, spider
            )
        except IgnoreRequest:
            pass
        self.populate_vars(response, request, spider)
        self.execute_code()

    def _open_spider(self, request, spider):
        if self.spider:
            return self.spider

        if spider is None:
            spider = self.crawler.spider or self.crawler._create_spider()

        self.crawler.spider = spider
        self.crawler.engine.open_spider(spider, close_if_idle=False)
        self.spider = spider
        return spider

    def populate_vars(self, response=None, request=None, spider=None):
        import scrapy

        self.vars = {
            "scrapy": scrapy,
            "crawler": self.crawler,
            "item": self.item_class(),
            "settings": self.crawler.settings,
            "spider": spider,
            "request": request,
            "response": response,
            "view": open_in_browser,
            "shelp": self.print_help,
        }
        if self.in_thread:
            self.vars["fetch"] = self.fetch
        self.update_vars(self.vars)
        if not self.code:
            self.vars["banner"] = self.get_help()

    def execute_code(self):
        if self.code:
            print(eval(self.code, globals(), self.vars))

    def get_help(self):
        return (
            "Available Scrapy objects:\n"
            "  scrapy     scrapy module (contains scrapy.Request, scrapy.Selector, etc)\n{}"
        ).format(
            '\n'.join(
                '  {key:<10} {value}'
                .format(key=k, value=v)
                for k, v in sorted(self.vars.items())
                if self._is_relevant(v)
            )
        )

    @staticmethod
    def print_help():
        print(ScrapyShell().get_help())

    @staticmethod
    def _is_relevant(value):
        return isinstance(value, ScrapyShell.objects) or is_item(value)


def inspect_response(response, spider):
    sigint_handler = signal.getsignal(signal.SIGINT)
    ScrapyShell(spider.crawler).start(response=response, spider=spider)
    signal.signal(signal.SIGINT, sigint_handler)


def _request_deferred(request):
    request_callback = request.callback
    request_errback = request.errback

    def _restore_callbacks(result):
        request.callback = request_callback
        request.errback = request_errback
        return result

    d = defer.Deferred()
    d.addBoth(_restore_callbacks)
    if request.callback:
        d.addCallbacks(request.callback, request.errback)

    request.callback, request.errback = d.callback, d.errback
    return d