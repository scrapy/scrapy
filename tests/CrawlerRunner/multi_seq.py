from twisted.internet.defer import inlineCallbacks
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


@inlineCallbacks
def main(reactor):
    configure_logging()
    runner = CrawlerRunner()
    yield runner.crawl(NoRequestsSpider)
    yield runner.crawl(NoRequestsSpider)


install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
react(main)
