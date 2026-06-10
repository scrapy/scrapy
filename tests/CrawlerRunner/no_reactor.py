from twisted.python import log

from scrapy import Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


configure_logging()
runner = CrawlerRunner()
d = runner.crawl(NoRequestsSpider)
d.addErrback(log.err)
