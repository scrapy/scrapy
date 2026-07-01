from scrapy.http import Request, Response
from scrapy.spidermiddlewares.start import StartSpiderMiddleware
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test


class TestMiddleware:
    @coroutine_test
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

    def test_spider_output_not_marked(self):
        # Requests from a non-None response (spider output) are not flagged.
        crawler = get_crawler(Spider)
        mw = build_from_crawler(StartSpiderMiddleware, crawler)
        response = Response("data:,")
        request = Request("data:,1")
        out = list(mw.process_spider_output(response, [request]))
        assert out == [request]
        assert "is_start_request" not in request.meta
