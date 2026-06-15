from twisted.internet.task import react

from scrapy import Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    custom_settings = {
        "TWISTED_REACTOR": None,
    }

    async def start(self):
        return
        yield


def main(reactor):
    configure_logging(
        {"LOG_FORMAT": "%(levelname)s: %(message)s", "LOG_LEVEL": "DEBUG"}
    )
    runner = CrawlerRunner()
    return runner.crawl(NoRequestsSpider)


react(main)
