import scrapy
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


scrapy.run(NoRequestsSpider, settings={"TWISTED_REACTOR_ENABLED": True})
