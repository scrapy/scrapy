# coding: utf-8
from scrapy.utils.asyncgen import as_async_generator


class ProcessStartRequestsAsyncGenMiddleware:
    async def process_start_requests(self, start_requests, spider):
        async for r in as_async_generator(start_requests):
            yield r
