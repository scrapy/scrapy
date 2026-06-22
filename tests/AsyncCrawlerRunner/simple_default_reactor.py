from twisted.internet.task import react

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


@deferred_f_from_coro_f
async def main(reactor):
    configure_logging()
    runner = AsyncCrawlerRunner()
    await runner.crawl(NoRequestsSpider)


react(main)
