from twisted.trial.unittest import TestCase

from scrapy.http import Request
from scrapy.spidermiddlewares.start import StartSpiderMiddleware
from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler


class TestMiddleware(TestCase):
    @deferred_f_from_coro_f
    async def test_async(self):
        crawler = get_crawler(Spider)
        mw = build_from_crawler(StartSpiderMiddleware, crawler)

        async def start():
            yield Request("data:,1")
            yield Request("data:,2", meta={"is_start_request": True})
            yield Request("data:,2", meta={"is_start_request": False})
            yield Request("data:,2", meta={"is_start_request": "foo"})

        result = [
            request.meta["is_start_request"]
            async for request in mw.process_start(start())
        ]
        assert result == [True, True, False, "foo"]

    @deferred_f_from_coro_f
    async def test_sync(self):
        crawler = get_crawler(Spider)
        mw = build_from_crawler(StartSpiderMiddleware, crawler)

        def start():
            yield Request("data:,1")
            yield Request("data:,2", meta={"is_start_request": True})
            yield Request("data:,2", meta={"is_start_request": False})
            yield Request("data:,2", meta={"is_start_request": "foo"})

        result = [
            request.meta["is_start_request"]
            for request in mw.process_start_requests(start(), Spider("test"))
        ]
        assert result == [True, True, False, "foo"]
