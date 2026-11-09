from twisted.internet.task import react

import scrapy
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.reactor import install_reactor
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


@deferred_f_from_coro_f
async def main(reactor) -> None:
    await scrapy.run_async(NoRequestsSpider)


install_reactor()
react(main)
