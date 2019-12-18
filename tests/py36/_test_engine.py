#coding: utf-8
import asyncio

from scrapy import Request

from tests.test_engine import TestSpider


class StartRequestsAsyncGenSpider(TestSpider):
    async def start_requests(self):
        for url in self.start_urls:
            yield Request(url, dont_filter=True)


class StartRequestsAsyncGenAsyncioSpider(TestSpider):
    async def start_requests(self):
        for url in self.start_urls:
            yield Request(url, dont_filter=True)
            await asyncio.sleep(0.1)
