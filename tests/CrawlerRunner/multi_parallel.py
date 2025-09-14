from twisted.internet.task import react

from scrapy import Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.reactor import install_reactor


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


def main(reactor):
    configure_logging()
    runner = CrawlerRunner()
    runner.crawl(NoRequestsSpider)
    runner.crawl(NoRequestsSpider)
    return runner.join()


install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
react(main)
