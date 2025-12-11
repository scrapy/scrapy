from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from logging import DEBUG
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, call
from urllib.parse import urlparse

import attr
import pytest
from itemadapter import ItemAdapter
from pydispatch import dispatcher
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks

from scrapy import signals
from scrapy.core.engine import ExecutionEngine, _Slot
from scrapy.core.scheduler import BaseScheduler
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Spider
from scrapy.utils.defer import (
    _schedule_coro,
    deferred_f_from_coro_f,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.signal import disconnect_all
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests import get_testdata

if TYPE_CHECKING:
    from scrapy.core.scheduler import Scheduler
    from scrapy.crawler import Crawler
    from scrapy.statscollectors import MemoryStatsCollector
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


class TestEngineBase:
    @staticmethod
    def _assert_visited_urls(run: CrawlerRun) -> None:
        must_be_visited = [
            "/static/",
            "/redirect",
            "/redirected",
            "/static/item1.html",
            "/static/item2.html",
            "/static/item999.html",
        ]
        urls_visited = {rp[0].url for rp in run.respplug}
        urls_expected = {run.geturl(p) for p in must_be_visited}
        assert urls_expected <= urls_visited, (
            f"URLs not visited: {list(urls_expected - urls_visited)}"
        )

    @staticmethod
    def _assert_scheduled_requests(run: CrawlerRun, count: int) -> None:
        assert len(run.reqplug) == count

        paths_expected = [
            "/static/item999.html",
            "/static/item2.html",
            "/static/item1.html",
        ]

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
            if run.getpath(response.url) == "/static/item999.html":
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
            if run.getpath(request.url) == "/static/":
                assert joined_data == get_testdata("test_site", "index.html")
            elif run.getpath(request.url) == "/static/item1.html":
                assert joined_data == get_testdata("test_site", "item1.html")
            elif run.getpath(request.url) == "/static/item2.html":
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
            elif run.getpath(request.url) == "/static/item999.html":
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
    @deferred_f_from_coro_f
    async def test_crawler(self, mockserver: MockServer) -> None:
        for spider in (
            MySpider,
            DictItemsSpider,
            AttrsItemsSpider,
            DataClassItemsSpider,
        ):
            run = CrawlerRun(spider)
            await run.run(mockserver)
            self._assert_visited_urls(run)
            self._assert_scheduled_requests(run, count=9)
            self._assert_downloaded_responses(run, count=9)
            self._assert_scraped_items(run)
            self._assert_signals_caught(run)
            self._assert_bytes_received(run)

    @deferred_f_from_coro_f
    async def test_crawler_dupefilter(self, mockserver: MockServer) -> None:
        run = CrawlerRun(DupeFilterSpider)
        await run.run(mockserver)
        self._assert_scheduled_requests(run, count=8)
        self._assert_dropped_requests(run)

    @deferred_f_from_coro_f
    async def test_crawler_itemerror(self, mockserver: MockServer) -> None:
        run = CrawlerRun(ItemZeroDivisionErrorSpider)
        await run.run(mockserver)
        self._assert_items_error(run)

    @deferred_f_from_coro_f
    async def test_crawler_change_close_reason_on_idle(
        self, mockserver: MockServer
    ) -> None:
        run = CrawlerRun(ChangeCloseReasonSpider)
        await run.run(mockserver)
        assert {
            "spider": run.crawler.spider,
            "reason": "custom_reason",
        } == run.signals_caught[signals.spider_closed]

    @deferred_f_from_coro_f
    async def test_close_downloader(self):
        e = ExecutionEngine(get_crawler(MySpider), lambda _: None)
        await e.close_async()

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

    @inlineCallbacks
    def test_start_already_running_exception(self):
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        e = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = e
        yield deferred_from_coro(e.open_spider_async())
        _schedule_coro(e.start_async())
        with pytest.raises(RuntimeError, match="Engine already running"):
            yield deferred_from_coro(e.start_async())
        yield deferred_from_coro(e.stop_async())

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_start_already_running_exception_asyncio(self):
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        e = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = e
        await e.open_spider_async()
        with pytest.raises(RuntimeError, match="Engine already running"):
            await asyncio.gather(e.start_async(), e.start_async())
        await e.stop_async()

    @inlineCallbacks
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        try:
            _, stderr = p.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            pytest.fail("Command took too much time to complete")

        stderr_str = stderr.decode("utf-8")
        assert "AttributeError" not in stderr_str, stderr_str
        assert "AssertionError" not in stderr_str, stderr_str


class TestEngineDownloadAsync:
    """Test cases for ExecutionEngine.download_async()."""

    @pytest.fixture
    def engine(self) -> ExecutionEngine:
        crawler = get_crawler(MySpider)
        engine = ExecutionEngine(crawler, lambda _: None)
        engine.downloader.close()
        engine.downloader = Mock()
        engine._slot = Mock()
        engine._slot.inprogress = set()
        return engine

    @staticmethod
    async def _download(engine: ExecutionEngine, request: Request) -> Response:
        return await engine.download_async(request)

    @deferred_f_from_coro_f
    async def test_download_async_success(self, engine):
        """Test basic successful async download of a request."""
        request = Request("http://example.com")
        response = Response("http://example.com", body=b"test body")
        engine.spider = Mock()
        engine.downloader.fetch.return_value = defer.succeed(response)
        engine._slot.add_request = Mock()
        engine._slot.remove_request = Mock()

        result = await self._download(engine, request)
        assert result == response
        engine._slot.add_request.assert_called_once_with(request)
        engine._slot.remove_request.assert_called_once_with(request)
        engine.downloader.fetch.assert_called_once_with(request)

    @deferred_f_from_coro_f
    async def test_download_async_redirect(self, engine):
        """Test async download with a redirect request."""
        original_request = Request("http://example.com")
        redirect_request = Request("http://example.com/redirect")
        final_response = Response("http://example.com/redirect", body=b"redirected")

        # First call returns redirect request, second call returns final response
        engine.downloader.fetch.side_effect = [
            defer.succeed(redirect_request),
            defer.succeed(final_response),
        ]
        engine.spider = Mock()
        engine._slot.add_request = Mock()
        engine._slot.remove_request = Mock()

        result = await self._download(engine, original_request)
        assert result == final_response
        assert engine.downloader.fetch.call_count == 2
        engine._slot.add_request.assert_has_calls(
            [call(original_request), call(redirect_request)]
        )
        engine._slot.remove_request.assert_has_calls(
            [call(original_request), call(redirect_request)]
        )

    @deferred_f_from_coro_f
    async def test_download_async_no_spider(self, engine):
        """Test async download attempt when no spider is available."""
        request = Request("http://example.com")
        engine.spider = None
        with pytest.raises(RuntimeError, match="No open spider to crawl:"):
            await self._download(engine, request)

    @deferred_f_from_coro_f
    async def test_download_async_failure(self, engine):
        """Test async download when the downloader raises an exception."""
        request = Request("http://example.com")
        error = RuntimeError("Download failed")
        engine.spider = Mock()
        engine.downloader.fetch.return_value = defer.fail(error)
        engine._slot.add_request = Mock()
        engine._slot.remove_request = Mock()

        with pytest.raises(RuntimeError, match="Download failed"):
            await self._download(engine, request)
        engine._slot.add_request.assert_called_once_with(request)
        engine._slot.remove_request.assert_called_once_with(request)


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestEngineDownload(TestEngineDownloadAsync):
    """Test cases for ExecutionEngine.download()."""

    @staticmethod
    async def _download(engine: ExecutionEngine, request: Request) -> Response:
        return await maybe_deferred_to_future(engine.download(request))


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
    crawler.signals.connect(signal_handler, signals.request_scheduled)
    keep_request = Request("https://keep.example")
    engine._schedule_request(keep_request)
    drop_request = Request("https://drop.example")
    caplog.set_level(DEBUG)
    engine._schedule_request(drop_request)
    assert scheduler.enqueued == [keep_request], (
        f"{scheduler.enqueued!r} != [{keep_request!r}]"
    )
    crawler.signals.disconnect(signal_handler, signals.request_scheduled)


class TestEngineCloseSpider:
    """Tests for exception handling coverage during close_spider_async()."""

    @pytest.fixture
    def crawler(self) -> Crawler:
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        return crawler

    @deferred_f_from_coro_f
    async def test_no_slot(self, crawler: Crawler) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        slot = engine._slot
        engine._slot = None
        with pytest.raises(RuntimeError, match="Engine slot not assigned"):
            await engine.close_spider_async()
        # close it correctly
        engine._slot = slot
        await engine.close_spider_async()

    @deferred_f_from_coro_f
    async def test_no_spider(self, crawler: Crawler) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        with pytest.raises(RuntimeError, match="Spider not opened"):
            await engine.close_spider_async()
        engine.downloader.close()  # cleanup

    @deferred_f_from_coro_f
    async def test_exception_slot(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        assert engine._slot
        del engine._slot.heartbeat
        await engine.close_spider_async()
        assert "Slot close failure" in caplog.text

    @deferred_f_from_coro_f
    async def test_exception_downloader(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        del engine.downloader.slots
        await engine.close_spider_async()
        assert "Downloader close failure" in caplog.text

    @deferred_f_from_coro_f
    async def test_exception_scraper(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        engine.scraper.slot = None
        await engine.close_spider_async()
        assert "Scraper close failure" in caplog.text

    @deferred_f_from_coro_f
    async def test_exception_scheduler(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        assert engine._slot
        del cast("Scheduler", engine._slot.scheduler).dqs
        await engine.close_spider_async()
        assert "Scheduler close failure" in caplog.text

    @deferred_f_from_coro_f
    async def test_exception_signal(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        signal_manager = engine.signals
        del engine.signals
        await engine.close_spider_async()
        assert "Error while sending spider_close signal" in caplog.text
        # send the spider_closed signal to close various components
        await signal_manager.send_catch_log_async(
            signal=signals.spider_closed,
            spider=engine.spider,
            reason="cancelled",
        )

    @deferred_f_from_coro_f
    async def test_exception_stats(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        del cast("MemoryStatsCollector", crawler.stats).spider_stats
        await engine.close_spider_async()
        assert "Stats close failure" in caplog.text

    @deferred_f_from_coro_f
    async def test_exception_callback(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: defer.fail(ValueError()))
        crawler.engine = engine
        await engine.open_spider_async()
        await engine.close_spider_async()
        assert "Error running spider_closed_callback" in caplog.text

    @deferred_f_from_coro_f
    async def test_exception_async_callback(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def cb(_):
            raise ValueError

        engine = ExecutionEngine(crawler, cb)
        crawler.engine = engine
        await engine.open_spider_async()
        await engine.close_spider_async()
        assert "Error running spider_closed_callback" in caplog.text
