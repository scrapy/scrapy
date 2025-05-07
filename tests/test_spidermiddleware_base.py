from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request, Spider
from scrapy.http import Response
from scrapy.spidermiddlewares.base import BaseSpiderMiddleware
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider)


def test_trivial(crawler):
    class TrivialSpiderMiddleware(BaseSpiderMiddleware):
        pass

    mw = TrivialSpiderMiddleware.from_crawler(crawler)
    assert hasattr(mw, "crawler")
    assert mw.crawler is crawler
    test_req = Request("data:,")
    spider_output = [test_req, {"foo": "bar"}]
    for processed in [
        list(
            mw.process_spider_output(Response("data:,"), spider_output, crawler.spider)
        ),
        list(mw.process_start_requests(spider_output, crawler.spider)),
    ]:
        assert processed == [test_req, {"foo": "bar"}]


def test_processed_request(crawler):
    class ProcessReqSpiderMiddleware(BaseSpiderMiddleware):
        def get_processed_request(
            self, request: Request, response: Response | None
        ) -> Request | None:
            if request.url == "data:2,":
                return None
            if request.url == "data:3,":
                return Request("data:30,")
            return request

    mw = ProcessReqSpiderMiddleware.from_crawler(crawler)
    test_req1 = Request("data:1,")
    test_req2 = Request("data:2,")
    test_req3 = Request("data:3,")
    spider_output = [test_req1, {"foo": "bar"}, test_req2, test_req3]
    for processed in [
        list(
            mw.process_spider_output(Response("data:,"), spider_output, crawler.spider)
        ),
        list(mw.process_start_requests(spider_output, crawler.spider)),
    ]:
        assert len(processed) == 3
        assert isinstance(processed[0], Request)
        assert processed[0].url == "data:1,"
        assert processed[1] == {"foo": "bar"}
        assert isinstance(processed[2], Request)
        assert processed[2].url == "data:30,"


def test_processed_item(crawler):
    class ProcessItemSpiderMiddleware(BaseSpiderMiddleware):
        def get_processed_item(self, item: Any, response: Response | None) -> Any:
            if item["foo"] == 2:
                return None
            if item["foo"] == 3:
                item["foo"] = 30
            return item

    mw = ProcessItemSpiderMiddleware.from_crawler(crawler)
    test_req = Request("data:,")
    spider_output = [{"foo": 1}, {"foo": 2}, test_req, {"foo": 3}]
    for processed in [
        list(
            mw.process_spider_output(Response("data:,"), spider_output, crawler.spider)
        ),
        list(mw.process_start_requests(spider_output, crawler.spider)),
    ]:
        assert processed == [{"foo": 1}, test_req, {"foo": 30}]


def test_processed_both(crawler):
    class ProcessBothSpiderMiddleware(BaseSpiderMiddleware):
        def get_processed_request(
            self, request: Request, response: Response | None
        ) -> Request | None:
            if request.url == "data:2,":
                return None
            if request.url == "data:3,":
                return Request("data:30,")
            return request

        def get_processed_item(self, item: Any, response: Response | None) -> Any:
            if item["foo"] == 2:
                return None
            if item["foo"] == 3:
                item["foo"] = 30
            return item

    mw = ProcessBothSpiderMiddleware.from_crawler(crawler)
    test_req1 = Request("data:1,")
    test_req2 = Request("data:2,")
    test_req3 = Request("data:3,")
    spider_output = [
        test_req1,
        {"foo": 1},
        {"foo": 2},
        test_req2,
        {"foo": 3},
        test_req3,
    ]
    for processed in [
        list(
            mw.process_spider_output(Response("data:,"), spider_output, crawler.spider)
        ),
        list(mw.process_start_requests(spider_output, crawler.spider)),
    ]:
        assert len(processed) == 4
        assert isinstance(processed[0], Request)
        assert processed[0].url == "data:1,"
        assert processed[1] == {"foo": 1}
        assert processed[2] == {"foo": 30}
        assert isinstance(processed[3], Request)
        assert processed[3].url == "data:30,"
