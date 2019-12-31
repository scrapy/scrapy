import asyncio

from scrapy import Request
from tests.spiders import SimpleSpider


class AsyncDefAsyncioGenSpider(SimpleSpider):

    name = 'asyncdef_asyncio_gen'

    async def parse(self, response):
        await asyncio.sleep(0.2)
        yield {'foo': 42}
        self.logger.info("Got response %d" % response.status)


class AsyncDefAsyncioGenLoopSpider(SimpleSpider):

    name = 'asyncdef_asyncio_gen_loop'

    async def parse(self, response):
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {'foo': i}
        self.logger.info("Got response %d" % response.status)


class AsyncDefAsyncioGenComplexSpider(SimpleSpider):

    name = 'asyncdef_asyncio_gen_complex'
    initial_reqs = 4
    following_reqs = 3
    depth = 2

    def _get_req(self, index):
        return Request(self.mockserver.url("/status?n=200&request=%d" % index),
                       meta={'index': index})

    def start_requests(self):
        for i in range(self.initial_reqs):
            yield self._get_req(i)

    async def parse(self, response):
        index = response.meta['index']
        yield {'index': index}
        if index < 10 ** self.depth:
            for new_index in range(10 * index, 10 * index + self.following_reqs):
                yield self._get_req(new_index)
        await asyncio.sleep(0.1)
        yield {'index': index + 5}
