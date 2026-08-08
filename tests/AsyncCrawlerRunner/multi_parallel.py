from twisted.internet.task import react

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.log import configure_logging
from scrapy.utils.reactor import install_reactor


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


@deferred_f_from_coro_f
async def main(reactor):
    configure_logging()
    runner = AsyncCrawlerRunner()
    runner.crawl(NoRequestsSpider)
    runner.crawl(NoRequestsSpider)
    await runner.join()


install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
react(main)
