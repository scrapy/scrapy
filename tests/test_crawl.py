from __future__ import annotations

import json
import logging
import unittest
from ipaddress import IPv4Address
from socket import gethostbyname
from typing import Any
from urllib.parse import urlparse

import pytest
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.internet.ssl import Certificate
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase

from scrapy import signals
from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import CloseSpider, StopDownload
from scrapy.http import Request
from scrapy.http.response import Response
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests import NON_EXISTING_RESOLVABLE
from tests.mockserver import MockServer
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


class TestCrawl(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_follow_all(self):
        crawler = get_crawler(FollowAllSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        assert len(crawler.spider.urls_visited) == 11  # 10 + start_url

    @defer.inlineCallbacks
    def test_fixed_delay(self):
        yield self._test_delay(total=3, delay=0.2)

    @defer.inlineCallbacks
    def test_randomized_delay(self):
        yield self._test_delay(total=3, delay=0.1, randomize=True)

    @defer.inlineCallbacks
    def _test_delay(self, total, delay, randomize=False):
        crawl_kwargs = {
            "maxlatency": delay * 2,
            "mockserver": self.mockserver,
            "total": total,
        }
        tolerance = 1 - (0.6 if randomize else 0.2)

        settings = {"DOWNLOAD_DELAY": delay, "RANDOMIZE_DOWNLOAD_DELAY": randomize}
        crawler = get_crawler(FollowAllSpider, settings)
        yield crawler.crawl(**crawl_kwargs)
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
        yield crawler.crawl(**crawl_kwargs)
        times = crawler.spider.times
        total_time = times[-1] - times[0]
        average = total_time / (len(times) - 1)
        assert average <= delay / tolerance, "test total or delay values are too small"

    @defer.inlineCallbacks
    def test_timeout_success(self):
        crawler = get_crawler(DelaySpider)
        yield crawler.crawl(n=0.5, mockserver=self.mockserver)
        assert crawler.spider.t1 > 0
        assert crawler.spider.t2 > 0
        assert crawler.spider.t2 > crawler.spider.t1

    @defer.inlineCallbacks
    def test_timeout_failure(self):
        crawler = get_crawler(DelaySpider, {"DOWNLOAD_TIMEOUT": 0.35})
        yield crawler.crawl(n=0.5, mockserver=self.mockserver)
        assert crawler.spider.t1 > 0
        assert crawler.spider.t2 == 0
        assert crawler.spider.t2_err > 0
        assert crawler.spider.t2_err > crawler.spider.t1

        # server hangs after receiving response headers
        crawler = get_crawler(DelaySpider, {"DOWNLOAD_TIMEOUT": 0.35})
        yield crawler.crawl(n=0.5, b=1, mockserver=self.mockserver)
        assert crawler.spider.t1 > 0
        assert crawler.spider.t2 == 0
        assert crawler.spider.t2_err > 0
        assert crawler.spider.t2_err > crawler.spider.t1

    @defer.inlineCallbacks
    def test_retry_503(self):
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/status?n=503"), mockserver=self.mockserver
            )
        self._assert_retried(log)

    @defer.inlineCallbacks
    def test_retry_conn_failed(self):
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                "http://localhost:65432/status?n=503", mockserver=self.mockserver
            )
        self._assert_retried(log)

    @defer.inlineCallbacks
    def test_retry_dns_error(self):
        if NON_EXISTING_RESOLVABLE:
            raise unittest.SkipTest("Non-existing hosts are resolvable")
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            # try to fetch the homepage of a nonexistent domain
            yield crawler.crawl(
                "http://dns.resolution.invalid./", mockserver=self.mockserver
            )
        self._assert_retried(log)

    @defer.inlineCallbacks
    def test_start_bug_before_yield(self):
        with LogCapture("scrapy", level=logging.ERROR) as log:
            crawler = get_crawler(BrokenStartSpider)
            yield crawler.crawl(fail_before_yield=1, mockserver=self.mockserver)

        assert len(log.records) == 1
        record = log.records[0]
        assert record.exc_info is not None
        assert record.exc_info[0] is ZeroDivisionError

    @defer.inlineCallbacks
    def test_start_bug_yielding(self):
        with LogCapture("scrapy", level=logging.ERROR) as log:
            crawler = get_crawler(BrokenStartSpider)
            yield crawler.crawl(fail_yielding=1, mockserver=self.mockserver)

        assert len(log.records) == 1
        record = log.records[0]
        assert record.exc_info is not None
        assert record.exc_info[0] is ZeroDivisionError

    @defer.inlineCallbacks
    def test_start_items(self):
        items = []

        def _on_item_scraped(item):
            items.append(item)

        with LogCapture("scrapy", level=logging.ERROR) as log:
            crawler = get_crawler(StartItemSpider)
            crawler.signals.connect(_on_item_scraped, signals.item_scraped)
            yield crawler.crawl(mockserver=self.mockserver)

        assert len(log.records) == 0
        assert items == [{"name": "test item"}]

    @defer.inlineCallbacks
    def test_start_unsupported_output(self):
        """Anything that is not a request is assumed to be an item, avoiding a
        potentially expensive call to itemadapter.is_item(), and letting
        instead things fail when ItemAdapter is actually used on the
        corresponding non-item object."""

        items = []

        def _on_item_scraped(item):
            items.append(item)

        with LogCapture("scrapy", level=logging.ERROR) as log:
            crawler = get_crawler(StartGoodAndBadOutput)
            crawler.signals.connect(_on_item_scraped, signals.item_scraped)
            yield crawler.crawl(mockserver=self.mockserver)

        assert len(log.records) == 0
        assert len(items) == 3
        assert not any(isinstance(item, Request) for item in items)

    @defer.inlineCallbacks
    def test_start_dupes(self):
        settings = {"CONCURRENT_REQUESTS": 1}
        crawler = get_crawler(DuplicateStartSpider, settings)
        yield crawler.crawl(
            dont_filter=True, distinct_urls=2, dupe_factor=3, mockserver=self.mockserver
        )
        assert crawler.spider.visited == 6

        crawler = get_crawler(DuplicateStartSpider, settings)
        yield crawler.crawl(
            dont_filter=False,
            distinct_urls=3,
            dupe_factor=4,
            mockserver=self.mockserver,
        )
        assert crawler.spider.visited == 3

    @defer.inlineCallbacks
    def test_unbounded_response(self):
        # Completeness of responses without Content-Length or Transfer-Encoding
        # can not be determined, we treat them as valid but flagged as "partial"
        from urllib.parse import urlencode

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
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url(f"/raw?{query}"), mockserver=self.mockserver
            )
        assert str(log).count("Got response 200") == 1

    @defer.inlineCallbacks
    def test_retry_conn_lost(self):
        # connection lost after receiving data
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/drop?abort=0"), mockserver=self.mockserver
            )
        self._assert_retried(log)

    @defer.inlineCallbacks
    def test_retry_conn_aborted(self):
        # connection lost before receiving data
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/drop?abort=1"), mockserver=self.mockserver
            )
        self._assert_retried(log)

    def _assert_retried(self, log):
        assert str(log).count("Retrying") == 2
        assert str(log).count("Gave up retrying") == 1

    @defer.inlineCallbacks
    def test_referer_header(self):
        """Referer header is set by RefererMiddleware unless it is already set"""
        req0 = Request(self.mockserver.url("/echo?headers=1&body=0"), dont_filter=1)
        req1 = req0.replace()
        req2 = req0.replace(headers={"Referer": None})
        req3 = req0.replace(headers={"Referer": "http://example.com"})
        req0.meta["next"] = req1
        req1.meta["next"] = req2
        req2.meta["next"] = req3
        crawler = get_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=req0, mockserver=self.mockserver)
        # basic asserts in case of weird communication errors
        assert "responses" in crawler.spider.meta
        assert "failures" not in crawler.spider.meta
        # start() doesn't set Referer header
        echo0 = json.loads(to_unicode(crawler.spider.meta["responses"][2].body))
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

    @defer.inlineCallbacks
    def test_engine_status(self):
        from scrapy.utils.engine import get_engine_status

        est = []

        def cb(response):
            est.append(get_engine_status(crawler.engine))

        crawler = get_crawler(SingleRequestSpider)
        yield crawler.crawl(
            seed=self.mockserver.url("/"), callback_func=cb, mockserver=self.mockserver
        )
        assert len(est) == 1, est
        s = dict(est[0])
        assert s["engine.spider.name"] == crawler.spider.name
        assert s["len(engine.scraper.slot.active)"] == 1

    @defer.inlineCallbacks
    def test_format_engine_status(self):
        from scrapy.utils.engine import format_engine_status

        est = []

        def cb(response):
            est.append(format_engine_status(crawler.engine))

        crawler = get_crawler(SingleRequestSpider)
        yield crawler.crawl(
            seed=self.mockserver.url("/"), callback_func=cb, mockserver=self.mockserver
        )
        assert len(est) == 1, est
        est = est[0].split("\n")[2:-2]  # remove header & footer
        # convert to dict
        est = [x.split(":") for x in est]
        est = [x for sublist in est for x in sublist]  # flatten
        est = [x.lstrip().rstrip() for x in est]
        it = iter(est)
        s = dict(zip(it, it))

        assert s["engine.spider.name"] == crawler.spider.name
        assert s["len(engine.scraper.slot.active)"] == "1"

    @defer.inlineCallbacks
    def test_open_spider_error_on_faulty_pipeline(self):
        settings = {
            "ITEM_PIPELINES": {
                "tests.pipelines.ZeroDivisionErrorPipeline": 300,
            }
        }
        crawler = get_crawler(SimpleSpider, settings)
        yield self.assertFailure(
            crawler.crawl(
                self.mockserver.url("/status?n=200"), mockserver=self.mockserver
            ),
            ZeroDivisionError,
        )
        assert not crawler.crawling

    @defer.inlineCallbacks
    def test_crawlerrunner_accepts_crawler(self):
        crawler = get_crawler(SimpleSpider)
        runner = CrawlerRunner()
        with LogCapture() as log:
            yield runner.crawl(
                crawler,
                self.mockserver.url("/status?n=200"),
                mockserver=self.mockserver,
            )
        assert "Got response 200" in str(log)

    @defer.inlineCallbacks
    def test_crawl_multiple(self):
        runner = CrawlerRunner(get_reactor_settings())
        runner.crawl(
            SimpleSpider,
            self.mockserver.url("/status?n=200"),
            mockserver=self.mockserver,
        )
        runner.crawl(
            SimpleSpider,
            self.mockserver.url("/status?n=503"),
            mockserver=self.mockserver,
        )

        with LogCapture() as log:
            yield runner.join()

        self._assert_retried(log)
        assert "Got response 200" in str(log)


class TestCrawlSpider(TestCase):
    mockserver: MockServer

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def _run_spider(self, spider_cls):
        items = []

        def _on_item_scraped(item):
            items.append(item)

        crawler = get_crawler(spider_cls)
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/status?n=200"), mockserver=self.mockserver
            )
        return log, items, crawler.stats

    @defer.inlineCallbacks
    def test_crawlspider_with_parse(self):
        crawler = get_crawler(CrawlSpiderWithParseMethod)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver)

        assert "[parse] status 200 (foo: None)" in str(log)
        assert "[parse] status 201 (foo: None)" in str(log)
        assert "[parse] status 202 (foo: bar)" in str(log)

    @defer.inlineCallbacks
    def test_crawlspider_with_async_callback(self):
        crawler = get_crawler(CrawlSpiderWithAsyncCallback)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver)

        assert "[parse_async] status 200 (foo: None)" in str(log)
        assert "[parse_async] status 201 (foo: None)" in str(log)
        assert "[parse_async] status 202 (foo: bar)" in str(log)

    @defer.inlineCallbacks
    def test_crawlspider_with_async_generator_callback(self):
        crawler = get_crawler(CrawlSpiderWithAsyncGeneratorCallback)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver)

        assert "[parse_async_gen] status 200 (foo: None)" in str(log)
        assert "[parse_async_gen] status 201 (foo: None)" in str(log)
        assert "[parse_async_gen] status 202 (foo: bar)" in str(log)

    @defer.inlineCallbacks
    def test_crawlspider_with_errback(self):
        crawler = get_crawler(CrawlSpiderWithErrback)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver)

        assert "[parse] status 200 (foo: None)" in str(log)
        assert "[parse] status 201 (foo: None)" in str(log)
        assert "[parse] status 202 (foo: bar)" in str(log)
        assert "[errback] status 404" in str(log)
        assert "[errback] status 500" in str(log)
        assert "[errback] status 501" in str(log)

    @defer.inlineCallbacks
    def test_crawlspider_process_request_cb_kwargs(self):
        crawler = get_crawler(CrawlSpiderWithProcessRequestCallbackKeywordArguments)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver)

        assert "[parse] status 200 (foo: process_request)" in str(log)
        assert "[parse] status 201 (foo: process_request)" in str(log)
        assert "[parse] status 202 (foo: bar)" in str(log)

    @defer.inlineCallbacks
    def test_async_def_parse(self):
        crawler = get_crawler(AsyncDefSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/status?n=200"), mockserver=self.mockserver
            )
        assert "Got response 200" in str(log)

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncio_parse(self):
        crawler = get_crawler(
            AsyncDefAsyncioSpider,
            {
                "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            },
        )
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/status?n=200"), mockserver=self.mockserver
            )
        assert "Got response 200" in str(log)

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncio_parse_items_list(self):
        log, items, _ = yield self._run_spider(AsyncDefAsyncioReturnSpider)
        assert "Got response 200" in str(log)
        assert {"id": 1} in items
        assert {"id": 2} in items

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncio_parse_items_single_element(self):
        items = []

        def _on_item_scraped(item):
            items.append(item)

        crawler = get_crawler(AsyncDefAsyncioReturnSingleElementSpider)
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/status?n=200"), mockserver=self.mockserver
            )
        assert "Got response 200" in str(log)
        assert {"foo": 42} in items

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncgen_parse(self):
        log, _, stats = yield self._run_spider(AsyncDefAsyncioGenSpider)
        assert "Got response 200" in str(log)
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 1

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncgen_parse_loop(self):
        log, items, stats = yield self._run_spider(AsyncDefAsyncioGenLoopSpider)
        assert "Got response 200" in str(log)
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 10
        for i in range(10):
            assert {"foo": i} in items

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncgen_parse_exc(self):
        log, items, stats = yield self._run_spider(AsyncDefAsyncioGenExcSpider)
        log = str(log)
        assert "Spider error processing" in log
        assert "ValueError" in log
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 7
        for i in range(7):
            assert {"foo": i} in items

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncgen_parse_complex(self):
        _, items, stats = yield self._run_spider(AsyncDefAsyncioGenComplexSpider)
        itemcount = stats.get_value("item_scraped_count")
        assert itemcount == 156
        # some random items
        for i in [1, 4, 21, 22, 207, 311]:
            assert {"index": i} in items
        for i in [10, 30, 122]:
            assert {"index2": i} in items

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_asyncio_parse_reqs_list(self):
        log, *_ = yield self._run_spider(AsyncDefAsyncioReqsReturnSpider)
        for req_id in range(3):
            assert f"Got response 200, req_id {req_id}" in str(log)

    @pytest.mark.only_not_asyncio
    @defer.inlineCallbacks
    def test_async_def_deferred_direct(self):
        _, items, _ = yield self._run_spider(AsyncDefDeferredDirectSpider)
        assert items == [{"code": 200}]

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_async_def_deferred_wrapped(self):
        log, items, _ = yield self._run_spider(AsyncDefDeferredWrappedSpider)
        assert items == [{"code": 200}]

    @defer.inlineCallbacks
    def test_async_def_deferred_maybe_wrapped(self):
        _, items, _ = yield self._run_spider(AsyncDefDeferredMaybeWrappedSpider)
        assert items == [{"code": 200}]

    @defer.inlineCallbacks
    def test_response_ssl_certificate_none(self):
        crawler = get_crawler(SingleRequestSpider)
        url = self.mockserver.url("/echo?body=test", is_secure=False)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        assert crawler.spider.meta["responses"][0].certificate is None

    @defer.inlineCallbacks
    def test_response_ssl_certificate(self):
        crawler = get_crawler(SingleRequestSpider)
        url = self.mockserver.url("/echo?body=test", is_secure=True)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        cert = crawler.spider.meta["responses"][0].certificate
        assert isinstance(cert, Certificate)
        assert cert.getSubject().commonName == b"localhost"
        assert cert.getIssuer().commonName == b"localhost"

    @pytest.mark.xfail(
        reason="Responses with no body return early and contain no certificate"
    )
    @defer.inlineCallbacks
    def test_response_ssl_certificate_empty_response(self):
        crawler = get_crawler(SingleRequestSpider)
        url = self.mockserver.url("/status?n=200", is_secure=True)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        cert = crawler.spider.meta["responses"][0].certificate
        assert isinstance(cert, Certificate)
        assert cert.getSubject().commonName == b"localhost"
        assert cert.getIssuer().commonName == b"localhost"

    @defer.inlineCallbacks
    def test_dns_server_ip_address_none(self):
        crawler = get_crawler(SingleRequestSpider)
        url = self.mockserver.url("/status?n=200")
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        ip_address = crawler.spider.meta["responses"][0].ip_address
        assert ip_address is None

    @defer.inlineCallbacks
    def test_dns_server_ip_address(self):
        crawler = get_crawler(SingleRequestSpider)
        url = self.mockserver.url("/echo?body=test")
        expected_netloc, _ = urlparse(url).netloc.split(":")
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        ip_address = crawler.spider.meta["responses"][0].ip_address
        assert isinstance(ip_address, IPv4Address)
        assert str(ip_address) == gethostbyname(expected_netloc)

    @defer.inlineCallbacks
    def test_bytes_received_stop_download_callback(self):
        crawler = get_crawler(BytesReceivedCallbackSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        assert crawler.spider.meta.get("failure") is None
        assert isinstance(crawler.spider.meta["response"], Response)
        assert crawler.spider.meta["response"].body == crawler.spider.meta.get(
            "bytes_received"
        )
        assert (
            len(crawler.spider.meta["response"].body)
            < crawler.spider.full_response_length
        )

    @defer.inlineCallbacks
    def test_bytes_received_stop_download_errback(self):
        crawler = get_crawler(BytesReceivedErrbackSpider)
        yield crawler.crawl(mockserver=self.mockserver)
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

    @defer.inlineCallbacks
    def test_headers_received_stop_download_callback(self):
        crawler = get_crawler(HeadersReceivedCallbackSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        assert crawler.spider.meta.get("failure") is None
        assert isinstance(crawler.spider.meta["response"], Response)
        assert crawler.spider.meta["response"].headers == crawler.spider.meta.get(
            "headers_received"
        )

    @defer.inlineCallbacks
    def test_headers_received_stop_download_errback(self):
        crawler = get_crawler(HeadersReceivedErrbackSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        assert crawler.spider.meta.get("response") is None
        assert isinstance(crawler.spider.meta["failure"], Failure)
        assert isinstance(crawler.spider.meta["failure"].value, StopDownload)
        assert isinstance(crawler.spider.meta["failure"].value.response, Response)
        assert crawler.spider.meta[
            "failure"
        ].value.response.headers == crawler.spider.meta.get("headers_received")

    @defer.inlineCallbacks
    def test_spider_errback(self):
        failures = []

        def eb(failure: Failure) -> Failure:
            failures.append(failure)
            return failure

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/status?n=400"), errback_func=eb
            )
        assert len(failures) == 1
        assert "HTTP status code is not handled or not allowed" in str(log)
        assert "Spider error processing" not in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_silence(self):
        failures = []

        def eb(failure: Failure) -> None:
            failures.append(failure)

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/status?n=400"), errback_func=eb
            )
        assert len(failures) == 1
        assert "HTTP status code is not handled or not allowed" not in str(log)
        assert "Spider error processing" not in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_exception(self):
        def eb(failure: Failure) -> None:
            raise ValueError("foo")

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/status?n=400"), errback_func=eb
            )
        assert "Spider error processing" in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_item(self):
        def eb(failure: Failure) -> Any:
            return {"foo": "bar"}

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/status?n=400"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in str(log)
        assert "Spider error processing" not in str(log)
        assert "'item_scraped_count': 1" in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_request(self):
        def eb(failure: Failure) -> Request:
            return Request(self.mockserver.url("/"))

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/status?n=400"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in str(log)
        assert "Spider error processing" not in str(log)
        assert "Crawled (200)" in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_downloader_error(self):
        failures = []

        def eb(failure: Failure) -> Failure:
            failures.append(failure)
            return failure

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert len(failures) == 1
        assert "Error downloading" in str(log)
        assert "Spider error processing" not in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_downloader_error_exception(self):
        def eb(failure: Failure) -> None:
            raise ValueError("foo")

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert "Error downloading" in str(log)
        assert "Spider error processing" in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_downloader_error_item(self):
        def eb(failure: Failure) -> Any:
            return {"foo": "bar"}

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in str(log)
        assert "Spider error processing" not in str(log)
        assert "'item_scraped_count': 1" in str(log)

    @defer.inlineCallbacks
    def test_spider_errback_downloader_error_request(self):
        def eb(failure: Failure) -> Request:
            return Request(self.mockserver.url("/"))

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                seed=self.mockserver.url("/drop?abort=1"), errback_func=eb
            )
        assert "HTTP status code is not handled or not allowed" not in str(log)
        assert "Spider error processing" not in str(log)
        assert "Crawled (200)" in str(log)

    @defer.inlineCallbacks
    def test_raise_closespider(self):
        def cb(response):
            raise CloseSpider

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(seed=self.mockserver.url("/"), callback_func=cb)
        assert "Closing spider (cancelled)" in str(log)
        assert "Spider error processing" not in str(log)

    @defer.inlineCallbacks
    def test_raise_closespider_reason(self):
        def cb(response):
            raise CloseSpider("my_reason")

        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(seed=self.mockserver.url("/"), callback_func=cb)
        assert "Closing spider (my_reason)" in str(log)
        assert "Spider error processing" not in str(log)
