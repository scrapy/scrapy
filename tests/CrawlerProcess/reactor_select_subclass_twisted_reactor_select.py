from twisted.internet.main import installReactor
from twisted.internet.selectreactor import SelectReactor
from twisted.python import log

import scrapy
from scrapy.crawler import CrawlerProcess


class SelectReactorSubclass(SelectReactor):
    pass


reactor = SelectReactorSubclass()
installReactor(reactor)


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    def start_requests(self):
        return []


process = CrawlerProcess(
    settings={
        "TWISTED_REACTOR": "twisted.internet.selectreactor.SelectReactor",
    }
)

d = process.crawl(NoRequestsSpider)
d.addErrback(log.err)
process.start()
