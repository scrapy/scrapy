from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import attr
from itemadapter import ItemAdapter
from twisted.internet import defer

from scrapy import signals
from scrapy.http import Headers, Request, Response
from scrapy.item import Field, Item
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Spider
from scrapy.utils import _signal_registry as dispatcher
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.signal import disconnect_all
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from twisted.python.failure import Failure

    from tests.mockserver.http import MockServer


class MyItem(Item):
    name = Field()
    url = Field()
    price = Field()


@attr.s
class AttrsItem:
    name = attr.ib(default="")
    url = attr.ib(default="")
    price = attr.ib(default=0)


@dataclass
class DataClassItem:
    name: str = ""
    url: str = ""
    price: int = 0


class MySpider(Spider):
    name = "scrapytest.org"

    itemurl_re = re.compile(r"item\d+.html")
    name_re = re.compile(r"<h1>(.*?)</h1>", re.MULTILINE)
    price_re = re.compile(r">Price: \$(.*?)<", re.MULTILINE)

    item_cls: type = MyItem

    def parse(self, response):
        xlink = LinkExtractor()
        itemre = re.compile(self.itemurl_re)
        for link in xlink.extract_links(response):
            if itemre.search(link.url):
                yield Request(url=link.url, callback=self.parse_item)

    def parse_item(self, response):
        adapter = ItemAdapter(self.item_cls())
        m = self.name_re.search(response.text)
        if m:
            adapter["name"] = m.group(1)
        adapter["url"] = response.url
        m = self.price_re.search(response.text)
        if m:
            adapter["price"] = m.group(1)
        return adapter.item


class DictItemsSpider(MySpider):
    item_cls = dict


class AttrsItemsSpider(MySpider):
    item_cls = AttrsItem


class DataClassItemsSpider(MySpider):
    item_cls = DataClassItem


class CrawlerRun:
    """A class to run the crawler and keep track of events occurred"""

    def __init__(self, spider_class: type[Spider]):
        self.respplug: list[tuple[Response, Spider]] = []
        self.reqplug: list[tuple[Request, Spider]] = []
        self.reqdropped: list[tuple[Request, Spider]] = []
        self.reqreached: list[tuple[Request, Spider]] = []
        self.itemerror: list[tuple[Any, Response, Spider, Failure]] = []
        self.itemresp: list[tuple[Any, Response]] = []
        self.headers: dict[Request, Headers] = {}
        self.bytes: defaultdict[Request, list[bytes]] = defaultdict(list)
        self.signals_caught: dict[Any, dict[str, Any]] = {}
        self.spider_class = spider_class

    async def run(self, mockserver: MockServer) -> None:
        self.mockserver = mockserver

        start_urls = [
            self.geturl("/static/"),
            self.geturl("/redirect"),
            self.geturl("/redirect"),  # duplicate
            self.geturl("/numbers"),
        ]

        for name, signal in vars(signals).items():
            if not name.startswith("_"):
                dispatcher.connect(self.record_signal, signal)

        self.crawler = get_crawler(self.spider_class)
        self.crawler.signals.connect(self.item_scraped, signals.item_scraped)
        self.crawler.signals.connect(self.item_error, signals.item_error)
        self.crawler.signals.connect(self.headers_received, signals.headers_received)
        self.crawler.signals.connect(self.bytes_received, signals.bytes_received)
        self.crawler.signals.connect(self.request_scheduled, signals.request_scheduled)
        self.crawler.signals.connect(self.request_dropped, signals.request_dropped)
        self.crawler.signals.connect(
            self.request_reached, signals.request_reached_downloader
        )
        self.crawler.signals.connect(
            self.response_downloaded, signals.response_downloaded
        )
        self.crawler.crawl(start_urls=start_urls)

        self.deferred: defer.Deferred[None] = defer.Deferred()
        dispatcher.connect(self.stop, signals.engine_stopped)
        await maybe_deferred_to_future(self.deferred)

    async def stop(self):
        for name, signal in vars(signals).items():
            if not name.startswith("_"):
                disconnect_all(signal)
        self.deferred.callback(None)
        await self.crawler.stop_async()

    def geturl(self, path: str) -> str:
        return self.mockserver.url(path)

    def getpath(self, url: str) -> str:
        u = urlparse(url)
        return u.path

    def item_error(
        self, item: Any, response: Response, spider: Spider, failure: Failure
    ) -> None:
        self.itemerror.append((item, response, spider, failure))

    def item_scraped(self, item: Any, spider: Spider, response: Response) -> None:
        self.itemresp.append((item, response))

    def headers_received(
        self, headers: Headers, body_length: int, request: Request, spider: Spider
    ) -> None:
        self.headers[request] = headers

    def bytes_received(self, data: bytes, request: Request, spider: Spider) -> None:
        self.bytes[request].append(data)

    def request_scheduled(self, request: Request, spider: Spider) -> None:
        self.reqplug.append((request, spider))

    def request_reached(self, request: Request, spider: Spider) -> None:
        self.reqreached.append((request, spider))

    def request_dropped(self, request: Request, spider: Spider) -> None:
        self.reqdropped.append((request, spider))

    def response_downloaded(self, response: Response, spider: Spider) -> None:
        self.respplug.append((response, spider))

    def record_signal(self, *args: Any, **kwargs: Any) -> None:
        """Record a signal and its parameters"""
        signalargs = kwargs.copy()
        sig = signalargs.pop("signal")
        signalargs.pop("sender", None)
        self.signals_caught[sig] = signalargs
