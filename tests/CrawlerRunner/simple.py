from twisted.internet.task import react

from scrapy import Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.reactor import install_reactor
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


def main(reactor):
    configure_logging()
    runner = CrawlerRunner()
    return runner.crawl(NoRequestsSpider)


install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
react(main)
