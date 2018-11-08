import asyncio

from tests.spiders import FollowAllSpider


class AioFollowAllSpider(FollowAllSpider):
    async def parse(self, response):
        for x in super().parse(response):
            await asyncio.sleep(0.01)
            yield x


# TODO check other styles:
#
#   async def parse(self, response):
#       await asyncio.sleep(0.01)
#       return {'item': 'result'}
#
#   async def parse(self, response):
#       await asyncio.sleep(0.01)
#       return scrapy.Request(url)
