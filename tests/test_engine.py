"""
Scrapy engine tests

This starts a testing web server (using twisted.server.Site) and then crawls it
with the Scrapy crawler.

To view the testing web server in a browser you can start it by running this
module with the ``runserver`` argument::

    python test_engine.py runserver
"""

import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from logging import DEBUG
from pathlib import Path
from threading import Timer
from unittest.mock import Mock
from urllib.parse import urlparse

import attr
import pytest
from itemadapter import ItemAdapter
from pydispatch import dispatcher
from testfixtures import LogCapture
from twisted.internet import defer, reactor
from twisted.trial import unittest
from twisted.web import server, static, util

from scrapy import signals
from scrapy.core.engine import ExecutionEngine, _Slot
from scrapy.core.scheduler import BaseScheduler
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http import Request
from scrapy.item import Field, Item
from scrapy.linkextractors import LinkExtractor
from scrapy.signals import request_scheduled
from scrapy.spiders import Spider
from scrapy.utils.signal import disconnect_all
from scrapy.utils.test import get_crawler
from tests import get_testdata, tests_datadir


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
    allowed_domains = ["scrapytest.org", "localhost"]

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


class DupeFilterSpider(MySpider):
    async def start(self):
        for url in self.start_urls:
            yield Request(url)  # no dont_filter=True


class DictItemsSpider(MySpider):
    item_cls = dict


class AttrsItemsSpider(MySpider):
    item_cls = AttrsItem


class DataClassItemsSpider(MySpider):
    item_cls = DataClassItem


class ItemZeroDivisionErrorSpider(MySpider):
    custom_settings = {
        "ITEM_PIPELINES": {
            "tests.pipelines.ProcessWithZeroDivisionErrorPipeline": 300,
        }
    }


class ChangeCloseReasonSpider(MySpider):
    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        crawler.signals.connect(spider.spider_idle, signals.spider_idle)
        return spider

    def spider_idle(self):
        raise CloseSpider(reason="custom_reason")


def start_test_site(debug=False):
    root_dir = Path(tests_datadir, "test_site")
    r = static.File(str(root_dir))
    r.putChild(b"redirect", util.Redirect(b"/redirected"))
    r.putChild(b"redirected", static.Data(b"Redirected here", "text/plain"))
    numbers = [str(x).encode("utf8") for x in range(2**18)]
    r.putChild(b"numbers", static.Data(b"".join(numbers), "text/plain"))

    port = reactor.listenTCP(0, server.Site(r), interface="127.0.0.1")
    if debug:
        print(
            f"Test server running at http://localhost:{port.getHost().port}/ "
            "- hit Ctrl-C to finish."
        )
    return port


class CrawlerRun:
    """A class to run the crawler and keep track of events occurred"""

    def __init__(self, spider_class):
        self.respplug = []
        self.reqplug = []
        self.reqdropped = []
        self.reqreached = []
        self.itemerror = []
        self.itemresp = []
        self.headers = {}
        self.bytes = defaultdict(list)
        self.signals_caught = {}
        self.spider_class = spider_class

    def run(self):
        self.port = start_test_site()
        self.portno = self.port.getHost().port

        start_urls = [
            self.geturl("/"),
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

        self.deferred = defer.Deferred()
        dispatcher.connect(self.stop, signals.engine_stopped)
        return self.deferred

    def stop(self):
        self.port.stopListening()  # FIXME: wait for this Deferred
        for name, signal in vars(signals).items():
            if not name.startswith("_"):
                disconnect_all(signal)
        self.deferred.callback(None)
        return self.crawler.stop()

    def geturl(self, path):
        return f"http://localhost:{self.portno}{path}"

    def getpath(self, url):
        u = urlparse(url)
        return u.path

    def item_error(self, item, response, spider, failure):
        self.itemerror.append((item, response, spider, failure))

    def item_scraped(self, item, spider, response):
        self.itemresp.append((item, response))

    def headers_received(self, headers, body_length, request, spider):
        self.headers[request] = headers

    def bytes_received(self, data, request, spider):
        self.bytes[request].append(data)

    def request_scheduled(self, request, spider):
        self.reqplug.append((request, spider))

    def request_reached(self, request, spider):
        self.reqreached.append((request, spider))

    def request_dropped(self, request, spider):
        self.reqdropped.append((request, spider))

    def response_downloaded(self, response, spider):
        self.respplug.append((response, spider))

    def record_signal(self, *args, **kwargs):
        """Record a signal and its parameters"""
        signalargs = kwargs.copy()
        sig = signalargs.pop("signal")
        signalargs.pop("sender", None)
        self.signals_caught[sig] = signalargs


class TestEngineBase(unittest.TestCase):
    @staticmethod
    def _assert_visited_urls(run: CrawlerRun) -> None:
        must_be_visited = [
            "/",
            "/redirect",
            "/redirected",
            "/item1.html",
            "/item2.html",
            "/item999.html",
        ]
        urls_visited = {rp[0].url for rp in run.respplug}
        urls_expected = {run.geturl(p) for p in must_be_visited}
        assert urls_expected <= urls_visited, (
            f"URLs not visited: {list(urls_expected - urls_visited)}"
        )

    @staticmethod
    def _assert_scheduled_requests(run: CrawlerRun, count: int) -> None:
        assert len(run.reqplug) == count

        paths_expected = ["/item999.html", "/item2.html", "/item1.html"]

        urls_requested = {rq[0].url for rq in run.reqplug}
        urls_expected = {run.geturl(p) for p in paths_expected}
        assert urls_expected <= urls_requested
        scheduled_requests_count = len(run.reqplug)
        dropped_requests_count = len(run.reqdropped)
        responses_count = len(run.respplug)
        assert scheduled_requests_count == dropped_requests_count + responses_count
        assert len(run.reqreached) == responses_count

    @staticmethod
    def _assert_dropped_requests(run: CrawlerRun) -> None:
        assert len(run.reqdropped) == 1

    @staticmethod
    def _assert_downloaded_responses(run: CrawlerRun, count: int) -> None:
        # response tests
        assert len(run.respplug) == count
        assert len(run.reqreached) == count

        for response, _ in run.respplug:
            if run.getpath(response.url) == "/item999.html":
                assert response.status == 404
            if run.getpath(response.url) == "/redirect":
                assert response.status == 302

    @staticmethod
    def _assert_items_error(run: CrawlerRun) -> None:
        assert len(run.itemerror) == 2
        for item, response, spider, failure in run.itemerror:
            assert failure.value.__class__ is ZeroDivisionError
            assert spider == run.crawler.spider

            assert item["url"] == response.url
            if "item1.html" in item["url"]:
                assert item["name"] == "Item 1 name"
                assert item["price"] == "100"
            if "item2.html" in item["url"]:
                assert item["name"] == "Item 2 name"
                assert item["price"] == "200"

    @staticmethod
    def _assert_scraped_items(run: CrawlerRun) -> None:
        assert len(run.itemresp) == 2
        for item, response in run.itemresp:
            item = ItemAdapter(item)
            assert item["url"] == response.url
            if "item1.html" in item["url"]:
                assert item["name"] == "Item 1 name"
                assert item["price"] == "100"
            if "item2.html" in item["url"]:
                assert item["name"] == "Item 2 name"
                assert item["price"] == "200"

    @staticmethod
    def _assert_headers_received(run: CrawlerRun) -> None:
        for headers in run.headers.values():
            assert b"Server" in headers
            assert b"TwistedWeb" in headers[b"Server"]
            assert b"Date" in headers
            assert b"Content-Type" in headers

    @staticmethod
    def _assert_bytes_received(run: CrawlerRun) -> None:
        assert len(run.bytes) == 9
        for request, data in run.bytes.items():
            joined_data = b"".join(data)
            if run.getpath(request.url) == "/":
                assert joined_data == get_testdata("test_site", "index.html")
            elif run.getpath(request.url) == "/item1.html":
                assert joined_data == get_testdata("test_site", "item1.html")
            elif run.getpath(request.url) == "/item2.html":
                assert joined_data == get_testdata("test_site", "item2.html")
            elif run.getpath(request.url) == "/redirected":
                assert joined_data == b"Redirected here"
            elif run.getpath(request.url) == "/redirect":
                assert (
                    joined_data == b"\n<html>\n"
                    b"    <head>\n"
                    b'        <meta http-equiv="refresh" content="0;URL=/redirected">\n'
                    b"    </head>\n"
                    b'    <body bgcolor="#FFFFFF" text="#000000">\n'
                    b'    <a href="/redirected">click here</a>\n'
                    b"    </body>\n"
                    b"</html>\n"
                )
            elif run.getpath(request.url) == "/tem999.html":
                assert (
                    joined_data == b"\n<html>\n"
                    b"  <head><title>404 - No Such Resource</title></head>\n"
                    b"  <body>\n"
                    b"    <h1>No Such Resource</h1>\n"
                    b"    <p>File not found.</p>\n"
                    b"  </body>\n"
                    b"</html>\n"
                )
            elif run.getpath(request.url) == "/numbers":
                # signal was fired multiple times
                assert len(data) > 1
                # bytes were received in order
                numbers = [str(x).encode("utf8") for x in range(2**18)]
                assert joined_data == b"".join(numbers)

    @staticmethod
    def _assert_signals_caught(run: CrawlerRun) -> None:
        assert signals.engine_started in run.signals_caught
        assert signals.engine_stopped in run.signals_caught
        assert signals.spider_opened in run.signals_caught
        assert signals.spider_idle in run.signals_caught
        assert signals.spider_closed in run.signals_caught
        assert signals.headers_received in run.signals_caught

        assert {"spider": run.crawler.spider} == run.signals_caught[
            signals.spider_opened
        ]
        assert {"spider": run.crawler.spider} == run.signals_caught[signals.spider_idle]
        assert {
            "spider": run.crawler.spider,
            "reason": "finished",
        } == run.signals_caught[signals.spider_closed]


class TestEngine(TestEngineBase):
    @defer.inlineCallbacks
    def test_crawler(self):
        for spider in (
            MySpider,
            DictItemsSpider,
            AttrsItemsSpider,
            DataClassItemsSpider,
        ):
            run = CrawlerRun(spider)
            yield run.run()
            self._assert_visited_urls(run)
            self._assert_scheduled_requests(run, count=9)
            self._assert_downloaded_responses(run, count=9)
            self._assert_scraped_items(run)
            self._assert_signals_caught(run)
            self._assert_bytes_received(run)

    @defer.inlineCallbacks
    def test_crawler_dupefilter(self):
        run = CrawlerRun(DupeFilterSpider)
        yield run.run()
        self._assert_scheduled_requests(run, count=8)
        self._assert_dropped_requests(run)

    @defer.inlineCallbacks
    def test_crawler_itemerror(self):
        run = CrawlerRun(ItemZeroDivisionErrorSpider)
        yield run.run()
        self._assert_items_error(run)

    @defer.inlineCallbacks
    def test_crawler_change_close_reason_on_idle(self):
        run = CrawlerRun(ChangeCloseReasonSpider)
        yield run.run()
        assert {
            "spider": run.crawler.spider,
            "reason": "custom_reason",
        } == run.signals_caught[signals.spider_closed]

    @defer.inlineCallbacks
    def test_close_downloader(self):
        e = ExecutionEngine(get_crawler(MySpider), lambda _: None)
        yield e.close()

    def test_close_without_downloader(self):
        class CustomException(Exception):
            pass

        class BadDownloader:
            def __init__(self, crawler):
                raise CustomException

        with pytest.raises(CustomException):
            ExecutionEngine(
                get_crawler(MySpider, {"DOWNLOADER": BadDownloader}), lambda _: None
            )

    @defer.inlineCallbacks
    def test_start_already_running_exception(self):
        e = ExecutionEngine(get_crawler(MySpider), lambda _: None)
        yield e.open_spider(MySpider())
        e.start()

        def cb(exc: BaseException) -> None:
            assert str(exc), "Engine already running"

        try:
            yield self.assertFailure(e.start(), RuntimeError).addBoth(cb)
        finally:
            yield e.stop()

    @defer.inlineCallbacks
    def test_start_request_processing_exception(self):
        class BadRequestFingerprinter:
            def fingerprint(self, request):
                raise ValueError  # to make Scheduler.enqueue_request() fail

        class SimpleSpider(Spider):
            name = "simple"

            async def start(self):
                yield Request("data:,")

        crawler = get_crawler(
            SimpleSpider, {"REQUEST_FINGERPRINTER_CLASS": BadRequestFingerprinter}
        )
        with LogCapture() as log:
            yield crawler.crawl()
        assert "Error while processing requests from start()" in str(log)
        assert "Spider closed (shutdown)" in str(log)

    def test_short_timeout(self):
        args = (
            sys.executable,
            "-m",
            "scrapy.cmdline",
            "fetch",
            "-s",
            "CLOSESPIDER_TIMEOUT=0.001",
            "-s",
            "LOG_LEVEL=DEBUG",
            "http://toscrape.com",
        )
        p = subprocess.Popen(
            args,
            stderr=subprocess.PIPE,
        )

        def kill_proc():
            p.kill()
            p.communicate()
            raise AssertionError("Command took too much time to complete")

        timer = Timer(15, kill_proc)
        try:
            timer.start()
            _, stderr = p.communicate()
        finally:
            timer.cancel()

        stderr_str = stderr.decode("utf-8")
        assert "AttributeError" not in stderr_str, stderr_str
        assert "AssertionError" not in stderr_str, stderr_str


def test_request_scheduled_signal(caplog):
    class TestScheduler(BaseScheduler):
        def __init__(self):
            self.enqueued = []

        def enqueue_request(self, request: Request) -> bool:
            self.enqueued.append(request)
            return True

    def signal_handler(request: Request, spider: Spider) -> None:
        if "drop" in request.url:
            raise IgnoreRequest

    crawler = get_crawler(MySpider)
    engine = ExecutionEngine(crawler, lambda _: None)
    engine.downloader._slot_gc_loop.stop()
    scheduler = TestScheduler()

    async def start():
        return
        yield

    engine._start = start()
    engine._slot = _Slot(False, Mock(), scheduler)
    crawler.signals.connect(signal_handler, request_scheduled)
    keep_request = Request("https://keep.example")
    engine._schedule_request(keep_request)
    drop_request = Request("https://drop.example")
    caplog.set_level(DEBUG)
    engine._schedule_request(drop_request)
    assert scheduler.enqueued == [keep_request], (
        f"{scheduler.enqueued!r} != [{keep_request!r}]"
    )
    crawler.signals.disconnect(signal_handler, request_scheduled)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "runserver":
        start_test_site(debug=True)
        reactor.run()
