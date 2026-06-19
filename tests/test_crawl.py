from __future__ import annotations

import json
import logging
from ipaddress import IPv4Address
from socket import gethostbyname
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse

import pytest
from cryptography.x509 import load_der_x509_certificate
from twisted.internet.defer import succeed
from twisted.internet.ssl import Certificate
from twisted.python.failure import Failure

from scrapy import Spider, signals
from scrapy.crawler import AsyncCrawlerRunner, CrawlerRunner
from scrapy.exceptions import CloseSpider, ScrapyDeprecationWarning, StopDownload
from scrapy.http import Request
from scrapy.http.response import Response
from scrapy.utils.defer import ensure_awaitable, maybe_deferred_to_future
from scrapy.utils.engine import format_engine_status, get_engine_status
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests import NON_EXISTING_RESOLVABLE
from tests.spiders import (
    AsyncDefAsyncioGenComplexSpider,
    AsyncDefAsyncioGenExcSpider,
    AsyncDefAsyncioGenLoopSpider,
    AsyncDefAsyncioGenSpider,
    AsyncDefAsyncioReqsReturnSpider,
    AsyncDefAsyncioReturnSingleElementSpider,
    AsyncDefAsyncioReturnSpider,
    AsyncDefAsyncioSpider,
    AsyncDefDeferredDirectSpider,
    AsyncDefDeferredMaybeWrappedSpider,
    AsyncDefDeferredWrappedSpider,
    AsyncDefSpider,
    BrokenStartSpider,
    BytesReceivedCallbackSpider,
    BytesReceivedErrbackSpider,
    CrawlSpiderWithAsyncCallback,
    CrawlSpiderWithAsyncGeneratorCallback,
    CrawlSpiderWithErrback,
    CrawlSpiderWithParseMethod,
    CrawlSpiderWithProcessRequestCallbackKeywordArguments,
    DelaySpider,
    DuplicateStartSpider,
    FollowAllSpider,
    HeadersReceivedCallbackSpider,
    HeadersReceivedErrbackSpider,
    SimpleSpider,
    SingleRequestSpider,
    StartGoodAndBadOutput,
    StartItemSpider,
)
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.statscollectors import StatsCollector
    from tests.mockserver.http import MockServer


class TestCrawl:
    @coroutine_test
    async def test_follow_all(self, mockserver: MockServer) -> None:
        crawler = get_crawler(FollowAllSpider)
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, FollowAllSpider)
        assert len(crawler.spider.urls_visited) == 11  # 10 + start_url

    @coroutine_test
    async def test_fixed_delay(self, mockserver: MockServer) -> None:
        await self._test_delay(mockserver, total=3, delay=0.2)

    @coroutine_test
    async def test_randomized_delay(self, mockserver: MockServer) -> None:
        await self._test_delay(mockserver, total=3, delay=0.1, randomize=True)

    @staticmethod
    async def _test_delay(
        mockserver: MockServer, total: int, delay: float, randomize: bool = False
    ) -> None:
        crawl_kwargs = {
            "maxlatency": delay * 2,
            "mockserver": mockserver,
            "total": total,
        }
        tolerance = 1 - (0.6 if randomize else 0.2)

        settings = {"DOWNLOAD_DELAY": delay, "RANDOMIZE_DOWNLOAD_DELAY": randomize}
        crawler = get_crawler(FollowAllSpider, settings)
        await crawler.crawl_async(**crawl_kwargs)
        assert crawler.spider
        assert isinstance(crawler.spider, FollowAllSpider)
        times = crawler.spider.times
        total_time = times[-1] - times[0]
        average = total_time / (len(times) - 1)
        assert average > delay * tolerance, f"download delay too small: {average}"

        # Ensure that the same test parameters would cause a failure if no
        # download delay is set. Otherwise, it means we are using a combination
        # of ``total`` and ``delay`` values that are too small for the test
        # code above to have any meaning.
        settings["DOWNLOAD_DELAY"] = 0
        crawler = get_crawler(FollowAllSpider, settings)
        await crawler.crawl_async(**crawl_kwargs)
        assert crawler.spider
        assert isinstance(crawler.spider, FollowAllSpider)
        times = crawler.spider.times
        total_time = times[-1] - times[0]
        average = total_time / (len(times) - 1)
        assert average <= delay / tolerance, "test total or delay values are too small"

    @coroutine_test
    async def test_timeout_success(self, mockserver: MockServer) -> None:
        crawler = get_crawler(DelaySpider)
        await crawler.crawl_async(n=0.5, mockserver=mockserver)
        assert isinstance(crawler.spider, DelaySpider)
        assert crawler.spider.t1 > 0
        assert crawler.spider.t2 > 0
        assert crawler.spider.t2 > crawler.spider.t1

    @coroutine_test
    async def test_timeout_failure(self, mockserver: MockServer) -> None:
        crawler = get_crawler(DelaySpider, {"DOWNLOAD_TIMEOUT": 0.35})
        await crawler.crawl_async(n=0.5, mockserver=mockserver)
        assert isinstance(crawler.spider, DelaySpider)
        assert crawler.spider.t1 > 0
        assert crawler.spider.t2 == 0
        assert crawler.spider.t2_err > 0
        assert crawler.spider.t2_err > crawler.spider.t1

        # server hangs after receiving response headers
        crawler = get_crawler(DelaySpider, {"DOWNLOAD_TIMEOUT": 0.35})
        await crawler.crawl_async(n=0.5, b=1, mockserver=mockserver)
        assert isinstance(crawler.spider, DelaySpider)
        assert crawler.spider.t1 > 0
        assert crawler.spider.t2 == 0
        assert crawler.spider.t2_err > 0
        assert crawler.spider.t2_err > crawler.spider.t1

    @coroutine_test
    async def test_retry_503(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(SimpleSpider)
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(
                mockserver.url("/status?n=503"), mockserver=mockserver
            )
        self._assert_retried(caplog.text)

    @coroutine_test
    async def test_retry_conn_failed(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(SimpleSpider)
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(
                "http://localhost:65432/status?n=503", mockserver=mockserver
            )
        self._assert_retried(caplog.text)

    @coroutine_test
    async def test_retry_dns_error(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        if NON_EXISTING_RESOLVABLE:
            pytest.skip("Non-existing hosts are resolvable")
        crawler = get_crawler(SimpleSpider)
        with caplog.at_level(logging.DEBUG):
            # try to fetch the homepage of a nonexistent domain
            await crawler.crawl_async(
                "http://dns.resolution.invalid./", mockserver=mockserver
            )
        self._assert_retried(caplog.text)

    @coroutine_test
    async def test_start_bug_before_yield(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        with caplog.at_level(logging.ERROR):
            crawler = get_crawler(BrokenStartSpider)
            await crawler.crawl_async(fail_before_yield=1, mockserver=mockserver)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.exc_info is not None
        assert record.exc_info[0] is ZeroDivisionError

    @coroutine_test
    async def test_start_bug_yielding(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        with caplog.at_level(logging.ERROR):
            crawler = get_crawler(BrokenStartSpider)
            await crawler.crawl_async(fail_yielding=1, mockserver=mockserver)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.exc_info is not None
        assert record.exc_info[0] is ZeroDivisionError

    @coroutine_test
    async def test_start_items(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        items = []

        def _on_item_scraped(item):
            items.append(item)

        with caplog.at_level(logging.ERROR):
            crawler = get_crawler(StartItemSpider)
            crawler.signals.connect(_on_item_scraped, signals.item_scraped)
            await crawler.crawl_async(mockserver=mockserver)

        assert len(caplog.records) == 0
        assert items == [{"name": "test item"}]

    @coroutine_test
    async def test_start_unsupported_output(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        """Anything that is not a request is assumed to be an item, avoiding a
        potentially expensive call to itemadapter.is_item(), and letting
        instead things fail when ItemAdapter is actually used on the
        corresponding non-item object."""

        items = []

        def _on_item_scraped(item):
            items.append(item)

        with caplog.at_level(logging.ERROR):
            crawler = get_crawler(StartGoodAndBadOutput)
            crawler.signals.connect(_on_item_scraped, signals.item_scraped)
            await crawler.crawl_async(mockserver=mockserver)

        assert len(caplog.records) == 0
        assert len(items) == 3
        assert not any(isinstance(item, Request) for item in items)

    @coroutine_test
    async def test_start_dupes(self, mockserver: MockServer) -> None:
        settings = {"CONCURRENT_REQUESTS": 1}
        crawler = get_crawler(DuplicateStartSpider, settings)
        await crawler.crawl_async(
            dont_filter=True, distinct_urls=2, dupe_factor=3, mockserver=mockserver
        )
        assert isinstance(crawler.spider, DuplicateStartSpider)
        assert crawler.spider.visited == 6

        crawler = get_crawler(DuplicateStartSpider, settings)
        await crawler.crawl_async(
            dont_filter=False,
            distinct_urls=3,
            dupe_factor=4,
            mockserver=mockserver,
        )
        assert isinstance(crawler.spider, DuplicateStartSpider)
        assert crawler.spider.visited == 3

    @coroutine_test
    async def test_unbounded_response(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        # Completeness of responses without Content-Length or Transfer-Encoding
        # can not be determined, we treat them as valid but flagged as "partial"
        query = urlencode(
            {
                "raw": """\
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1
X-Powered-By: Servlet 2.4; JBoss-4.2.3.GA (build: SVNTag=JBoss_4_2_3_GA date=200807181417)/JBossWeb-2.0
Set-Cookie: JSESSIONID=08515F572832D0E659FD2B0D8031D75F; Path=/
Pragma: no-cache
Expires: Thu, 01 Jan 1970 00:00:00 GMT
Cache-Control: no-cache
Cache-Control: no-store
Content-Type: text/html;charset=UTF-8
Content-Language: en
Date: Tue, 27 Aug 2013 13:05:05 GMT
Connection: close

foo body
with multiples lines
"""
            }
        )
        crawler = get_crawler(SimpleSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                mockserver.url(f"/raw?{query}"), mockserver=mockserver
            )
        assert caplog.text.count("Got response 200") == 1

    @coroutine_test
    async def test_retry_conn_lost(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        # connection lost after receiving data
        crawler = get_crawler(SimpleSpider)
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(
                mockserver.url("/drop?abort=0"), mockserver=mockserver
            )
        self._assert_retried(caplog.text)

    @coroutine_test
    async def test_retry_conn_aborted(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        # connection lost before receiving data
        crawler = get_crawler(SimpleSpider)
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(
                mockserver.url("/drop?abort=1"), mockserver=mockserver
            )
        self._assert_retried(caplog.text)

    @staticmethod
    def _assert_retried(log: str) -> None:
        assert str(log).count("Retrying") == 2
        assert str(log).count("Gave up retrying") == 1

    @coroutine_test
    async def test_referer_header(self, mockserver: MockServer) -> None:
        """Referer header is set by RefererMiddleware unless it is already set"""
        req0 = Request(mockserver.url("/echo?headers=1&body=0"), dont_filter=True)
        req1 = req0.replace()
        req2 = req0.replace(headers={"Referer": None})
        req3 = req0.replace(headers={"Referer": "http://example.com"})
        req0.meta["next"] = req1
        req1.meta["next"] = req2
        req2.meta["next"] = req3
        crawler = get_crawler(SingleRequestSpider)
        await crawler.crawl_async(seed=req0, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        # basic asserts in case of weird communication errors
        assert "responses" in crawler.spider.meta
        assert "failures" not in crawler.spider.meta
        # start() doesn't set Referer header
        echo0 = json.loads(to_unicode(crawler.spider.meta["responses"][0].body))
        assert "Referer" not in echo0["headers"]
        # following request sets Referer to the source request url
        echo1 = json.loads(to_unicode(crawler.spider.meta["responses"][1].body))
        assert echo1["headers"].get("Referer") == [req0.url]
        # next request avoids Referer header
        echo2 = json.loads(to_unicode(crawler.spider.meta["responses"][2].body))
        assert "Referer" not in echo2["headers"]
        # last request explicitly sets a Referer header
        echo3 = json.loads(to_unicode(crawler.spider.meta["responses"][3].body))
        assert echo3["headers"].get("Referer") == ["http://example.com"]

    @coroutine_test
    async def test_engine_status(self, mockserver: MockServer) -> None:
        est = []

        def cb(response):
            est.append(get_engine_status(crawler.engine))

        crawler = get_crawler(SingleRequestSpider)
        await crawler.crawl_async(
            seed=mockserver.url("/"), callback_func=cb, mockserver=mockserver
        )
        assert isinstance(crawler.spider, SingleRequestSpider)
        assert len(est) == 1, est
        s = dict(est[0])
        assert s["engine.spider.name"] == crawler.spider.name
        assert s["len(engine.scraper.slot.active)"] == 1

    @coroutine_test
    async def test_format_engine_status(self, mockserver: MockServer) -> None:
        est = []

        def cb(response):
            est.append(format_engine_status(crawler.engine))

        crawler = get_crawler(SingleRequestSpider)
        await crawler.crawl_async(
            seed=mockserver.url("/"), callback_func=cb, mockserver=mockserver
        )
        assert isinstance(crawler.spider, SingleRequestSpider)
        assert len(est) == 1, est
        est = est[0].split("\n")[2:-2]  # remove header & footer
        # convert to dict
        est = [x.split(":") for x in est]
        est = [x for sublist in est for x in sublist]  # flatten
        est = [x.lstrip().rstrip() for x in est]
        it = iter(est)
        s = dict(zip(it, it, strict=True))

        assert s["engine.spider.name"] == crawler.spider.name
        assert s["len(engine.scraper.slot.active)"] == "1"

    @coroutine_test
    async def test_open_spider_error_on_faulty_pipeline(
        self, mockserver: MockServer
    ) -> None:
        settings = {
            "ITEM_PIPELINES": {
                "tests.pipelines.ZeroDivisionErrorPipeline": 300,
            }
        }
        crawler = get_crawler(SimpleSpider, settings)
        with pytest.raises(ZeroDivisionError):
            await crawler.crawl_async(
                mockserver.url("/status?n=200"), mockserver=mockserver
            )
        assert not crawler.crawling

    @coroutine_test
    async def test_open_spider_error_on_faulty_pipeline_crawl(
        self, mockserver: MockServer
    ) -> None:
        # cover the except block in Crawler.crawl()
        settings = {
            "ITEM_PIPELINES": {
                "tests.pipelines.ZeroDivisionErrorPipeline": 300,
            }
        }
        crawler = get_crawler(SimpleSpider, settings)
        with pytest.raises(ZeroDivisionError):
            await maybe_deferred_to_future(
                crawler.crawl(mockserver.url("/status?n=200"), mockserver=mockserver)
            )
        assert not crawler.crawling

    @coroutine_test
    async def test_crawlerrunner_accepts_crawler(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(SimpleSpider)
        runner = CrawlerRunner()
        with caplog.at_level(logging.DEBUG):
            await maybe_deferred_to_future(
                runner.crawl(
                    crawler,
                    mockserver.url("/status?n=200"),
                    mockserver=mockserver,
                )
            )
        assert "Got response 200" in caplog.text

    @coroutine_test
    async def test_crawl_multiple(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        settings_dict = get_reactor_settings()
        runner_cls = (
            CrawlerRunner
            if settings_dict.get("TWISTED_REACTOR_ENABLED", True)
            else AsyncCrawlerRunner
        )
        runner = runner_cls(settings_dict)
        runner.crawl(
            SimpleSpider,
            mockserver.url("/status?n=200"),
            mockserver=mockserver,
        )
        runner.crawl(
            SimpleSpider,
            mockserver.url("/status?n=503"),
            mockserver=mockserver,
        )

        with caplog.at_level(logging.DEBUG):
            await ensure_awaitable(runner.join())

        self._assert_retried(caplog.text)
        assert "Got response 200" in caplog.text

    @coroutine_test
    async def test_unknown_url_scheme(self, caplog: pytest.LogCaptureFixture) -> None:
        crawler = get_crawler(SimpleSpider)
        await crawler.crawl_async("foo://bar")
        assert "NotSupported: Unsupported URL scheme 'foo'" in caplog.text


class TestCrawlSpider:
    @staticmethod
    async def _run_spider(
        spider_cls: type[Spider], mockserver: MockServer
    ) -> tuple[list[Any], StatsCollector]:
        items = []

        def _on_item_scraped(item):
            items.append(item)

        crawler = get_crawler(spider_cls)
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        await crawler.crawl_async(
            mockserver.url("/status?n=200"), mockserver=mockserver
        )
        assert crawler.stats
        return items, crawler.stats

    @coroutine_test
    async def test_crawlspider_with_parse(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(CrawlSpiderWithParseMethod)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(mockserver=mockserver)

        assert "[parse] status 200 (foo: None)" in caplog.text
        assert "[parse] status 201 (foo: None)" in caplog.text
        assert "[parse] status 202 (foo: bar)" in caplog.text

    @coroutine_test
    async def test_crawlspider_with_async_callback(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(CrawlSpiderWithAsyncCallback)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(mockserver=mockserver)

        assert "[parse_async] status 200 (foo: None)" in caplog.text
        assert "[parse_async] status 201 (foo: None)" in caplog.text
        assert "[parse_async] status 202 (foo: bar)" in caplog.text

    @coroutine_test
    async def test_crawlspider_with_async_generator_callback(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(CrawlSpiderWithAsyncGeneratorCallback)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(mockserver=mockserver)

        assert "[parse_async_gen] status 200 (foo: None)" in caplog.text
        assert "[parse_async_gen] status 201 (foo: None)" in caplog.text
        assert "[parse_async_gen] status 202 (foo: bar)" in caplog.text

    @coroutine_test
    async def test_crawlspider_with_errback(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(CrawlSpiderWithErrback)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(mockserver=mockserver)

        assert "[parse] status 200 (foo: None)" in caplog.text
        assert "[parse] status 201 (foo: None)" in caplog.text
        assert "[parse] status 202 (foo: bar)" in caplog.text
        assert "[errback] status 404" in caplog.text
        assert "[errback] status 500" in caplog.text
        assert "[errback] status 501" in caplog.text

    @coroutine_test
    async def test_crawlspider_process_request_cb_kwargs(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(CrawlSpiderWithProcessRequestCallbackKeywordArguments)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(mockserver=mockserver)

        assert "[parse] status 200 (foo: process_request)" in caplog.text
        assert "[parse] status 201 (foo: process_request)" in caplog.text
        assert "[parse] status 202 (foo: bar)" in caplog.text

    @coroutine_test
    async def test_async_def_parse(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(AsyncDefSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                mockserver.url("/status?n=200"), mockserver=mockserver
            )
        assert "Got response 200" in caplog.text

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncio_parse(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(
            AsyncDefAsyncioSpider,
            {
                "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            },
        )
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                mockserver.url("/status?n=200"), mockserver=mockserver
            )
        assert "Got response 200" in caplog.text

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncio_parse_items_list(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        with caplog.at_level(logging.INFO):
            items, _ = await self._run_spider(AsyncDefAsyncioReturnSpider, mockserver)
        assert "Got response 200" in caplog.text
        assert {"id": 1} in items
        assert {"id": 2} in items

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncio_parse_items_single_element(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        items = []

        def _on_item_scraped(item):
            items.append(item)

        crawler = get_crawler(AsyncDefAsyncioReturnSingleElementSpider)
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                mockserver.url("/status?n=200"), mockserver=mockserver
            )
        assert "Got response 200" in caplog.text
        assert {"foo": 42} in items

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncgen_parse(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        with caplog.at_level(logging.INFO):
            _, stats = await self._run_spider(AsyncDefAsyncioGenSpider, mockserver)
        assert "Got response 200" in caplog.text
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 1

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncgen_parse_loop(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        with caplog.at_level(logging.INFO):
            items, stats = await self._run_spider(
                AsyncDefAsyncioGenLoopSpider, mockserver
            )
        assert "Got response 200" in caplog.text
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 10
        for i in range(10):
            assert {"foo": i} in items

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncgen_parse_exc(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        with caplog.at_level(logging.INFO):
            items, stats = await self._run_spider(
                AsyncDefAsyncioGenExcSpider, mockserver
            )
        assert "Spider error processing" in caplog.text
        assert "ValueError" in caplog.text
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 7
        for i in range(7):
            assert {"foo": i} in items

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncgen_parse_complex(
        self, mockserver: MockServer
    ) -> None:
        items, stats = await self._run_spider(
            AsyncDefAsyncioGenComplexSpider, mockserver
        )
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 156
        # some random items
        for i in [1, 4, 21, 22, 207, 311]:
            assert {"index": i} in items
        for i in [10, 30, 122]:
            assert {"index2": i} in items

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_asyncio_parse_reqs_list(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        with caplog.at_level(logging.INFO):
            await self._run_spider(AsyncDefAsyncioReqsReturnSpider, mockserver)
        for req_id in range(3):
            assert f"Got response 200, req_id {req_id}" in caplog.text

    @pytest.mark.only_not_asyncio
    @coroutine_test
    async def test_async_def_deferred_direct(self, mockserver: MockServer) -> None:
        items, _ = await self._run_spider(AsyncDefDeferredDirectSpider, mockserver)
        assert items == [{"code": 200}]

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_async_def_deferred_wrapped(self, mockserver: MockServer) -> None:
        items, _ = await self._run_spider(AsyncDefDeferredWrappedSpider, mockserver)
        assert items == [{"code": 200}]

    @coroutine_test
    async def test_async_def_deferred_maybe_wrapped(
        self, mockserver: MockServer
    ) -> None:
        items, _ = await self._run_spider(
            AsyncDefDeferredMaybeWrappedSpider, mockserver
        )
        assert items == [{"code": 200}]

    @coroutine_test
    async def test_response_ssl_certificate_none(self, mockserver: MockServer) -> None:
        crawler = get_crawler(SingleRequestSpider)
        url = mockserver.url("/echo?body=test", is_secure=False)
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        assert crawler.spider.meta["responses"][0].certificate is None

    @pytest.mark.parametrize(
        "url",
        [
            "/echo?body=test",
            pytest.param(
                "/status?n=200",
                marks=pytest.mark.xfail(
                    'config.getoption("--reactor") != "none"',
                    reason="With HTTP11DownloadHandler, responses with no body are returned early and contain no certificate",
                    strict=True,
                ),
            ),
        ],
    )
    @coroutine_test
    async def test_response_ssl_certificate(
        self, mockserver: MockServer, url: str
    ) -> None:
        crawler = get_crawler(SingleRequestSpider)
        url = mockserver.url(url, is_secure=True)
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        cert = crawler.spider.meta["responses"][0].certificate
        assert cert is not None
        if isinstance(cert, Certificate):  # Twisted
            assert cert.getSubject().commonName == b"localhost"
            assert cert.getIssuer().commonName == b"localhost"
        elif isinstance(cert, bytes):  # DER bytes
            cert_x509 = load_der_x509_certificate(cert)
            assert cert_x509.subject.rfc4514_string() == "CN=localhost,O=Scrapy,C=IE"
            assert cert_x509.issuer.rfc4514_string() == "CN=localhost,O=Scrapy,C=IE"

    @pytest.mark.parametrize(
        "url",
        [
            "/echo?body=test",
            pytest.param(
                "/status?n=200",
                marks=pytest.mark.xfail(
                    'config.getoption("--reactor") != "none"',
                    reason="With HTTP11DownloadHandler, responses with no body are returned early and contain no ip_address",
                    strict=True,
                ),
            ),
        ],
    )
    @coroutine_test
    async def test_response_ip_address(self, mockserver: MockServer, url: str) -> None:
        crawler = get_crawler(SingleRequestSpider)
        url = mockserver.url(url)
        expected_netloc, _ = urlparse(url).netloc.split(":")
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        ip_address = crawler.spider.meta["responses"][0].ip_address
        assert isinstance(ip_address, IPv4Address)
        assert str(ip_address) == gethostbyname(expected_netloc)

    @coroutine_test
    async def test_bytes_received_stop_download_callback(
        self, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(BytesReceivedCallbackSpider)
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, BytesReceivedCallbackSpider)
        assert crawler.spider.meta.get("failure") is None
        assert isinstance(crawler.spider.meta["response"], Response)
        assert crawler.spider.meta["response"].body == crawler.spider.meta.get(
            "bytes_received"
        )
        assert (
            len(crawler.spider.meta["response"].body)
            < crawler.spider.full_response_length
        )

    @coroutine_test
    async def test_bytes_received_stop_download_errback(
        self, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(BytesReceivedErrbackSpider)
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, BytesReceivedErrbackSpider)
        assert crawler.spider.meta.get("response") is None
        assert isinstance(crawler.spider.meta["failure"], Failure)
        assert isinstance(crawler.spider.meta["failure"].value, StopDownload)
        assert isinstance(crawler.spider.meta["failure"].value.response, Response)
        assert crawler.spider.meta[
            "failure"
        ].value.response.body == crawler.spider.meta.get("bytes_received")
        assert (
            len(crawler.spider.meta["failure"].value.response.body)
            < crawler.spider.full_response_length
        )

    @coroutine_test
    async def test_headers_received_stop_download_callback(
        self, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(HeadersReceivedCallbackSpider)
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, HeadersReceivedCallbackSpider)
        assert crawler.spider.meta.get("failure") is None
        assert isinstance(crawler.spider.meta["response"], Response)
        assert crawler.spider.meta["response"].headers == crawler.spider.meta.get(
            "headers_received"
        )

    @coroutine_test
    async def test_headers_received_stop_download_errback(
        self, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(HeadersReceivedErrbackSpider)
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, HeadersReceivedErrbackSpider)
        assert crawler.spider.meta.get("response") is None
        assert isinstance(crawler.spider.meta["failure"], Failure)
        assert isinstance(crawler.spider.meta["failure"].value, StopDownload)
        assert isinstance(crawler.spider.meta["failure"].value.response, Response)
        assert crawler.spider.meta[
            "failure"
        ].value.response.headers == crawler.spider.meta.get("headers_received")

    @coroutine_test
    async def test_spider_callback_deferred_deprecated(
        self, mockserver: MockServer
    ) -> None:
        def cb(response: Response) -> Any:
            return succeed(None)

        crawler = get_crawler(SingleRequestSpider)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="Returning Deferreds from spider callbacks is deprecated",
        ):
            await crawler.crawl_async(seed=mockserver.url("/"), callback_func=cb)

    @coroutine_test
    async def test_spider_errback(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        failures = []

        def eb(failure: Failure) -> Failure:
            failures.append(failure)
            return failure

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                seed=mockserver.url("/status?n=400"), errback_func=eb
            )
        assert len(failures) == 1
        assert "HTTP status code is not handled or not allowed" in caplog.text
        assert "Spider error processing" not in caplog.text

    @coroutine_test
    async def test_spider_errback_silence(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        failures = []

        def eb(failure: Failure) -> None:
            failures.append(failure)

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                seed=mockserver.url("/status?n=400"), errback_func=eb
            )
        assert len(failures) == 1
        assert "HTTP status code is not handled or not allowed" not in caplog.text
        assert "Spider error processing" not in caplog.text

    @coroutine_test
    async def test_spider_errback_exception(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def eb(failure: Failure) -> None:
            raise ValueError("foo")

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                seed=mockserver.url("/status?n=400"), errback_func=eb
            )
        assert "Spider error processing" in caplog.text

    @coroutine_test
    async def test_spider_errback_item(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def eb(failure: Failure) -> Any:
            return {"foo": "bar"}

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                seed=mockserver.url("/status?n=400"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in caplog.text
        assert "Spider error processing" not in caplog.text
        assert "'item_scraped_count': 1" in caplog.text

    @coroutine_test
    async def test_spider_errback_request(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def eb(failure: Failure) -> Request:
            return Request(mockserver.url("/"))

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(
                seed=mockserver.url("/status?n=400"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in caplog.text
        assert "Spider error processing" not in caplog.text
        assert "Crawled (200)" in caplog.text

    @coroutine_test
    async def test_spider_errback_downloader_error(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        failures = []

        def eb(failure: Failure) -> Failure:
            failures.append(failure)
            return failure

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                seed=mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert len(failures) == 1
        assert "Error downloading" in caplog.text
        assert "Spider error processing" not in caplog.text

    @coroutine_test
    async def test_spider_errback_downloader_error_exception(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def eb(failure: Failure) -> None:
            raise ValueError("foo")

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                seed=mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert "Error downloading" in caplog.text
        assert "Spider error processing" in caplog.text

    @coroutine_test
    async def test_spider_errback_downloader_error_item(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def eb(failure: Failure) -> Any:
            return {"foo": "bar"}

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(
                seed=mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in caplog.text
        assert "Spider error processing" not in caplog.text
        assert "'item_scraped_count': 1" in caplog.text

    @coroutine_test
    async def test_spider_errback_downloader_error_request(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def eb(failure: Failure) -> Request:
            return Request(mockserver.url("/"))

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(
                seed=mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in caplog.text
        assert "Spider error processing" not in caplog.text
        assert "Crawled (200)" in caplog.text

    @coroutine_test
    async def test_spider_errback_deferred_deprecated(
        self, mockserver: MockServer
    ) -> None:
        def eb(failure: Failure) -> Any:
            return succeed(None)

        crawler = get_crawler(SingleRequestSpider)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="Returning Deferreds from spider errbacks is deprecated",
        ):
            await crawler.crawl_async(
                seed=mockserver.url("/status?n=400"), errback_func=eb
            )

    @coroutine_test
    async def test_raise_closespider(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def cb(response):
            raise CloseSpider

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(seed=mockserver.url("/"), callback_func=cb)
        assert "Closing spider (cancelled)" in caplog.text
        assert "Spider error processing" not in caplog.text

    @coroutine_test
    async def test_raise_closespider_reason(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        def cb(response):
            raise CloseSpider("my_reason")

        crawler = get_crawler(SingleRequestSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(seed=mockserver.url("/"), callback_func=cb)
        assert "Closing spider (my_reason)" in caplog.text
        assert "Spider error processing" not in caplog.text
