import scrapy
from scrapy.crawler import CrawlerProcess
from twisted.internet.main import installReactor
from twisted.internet.selectreactor import SelectReactor


class SelectReactorSubclass(SelectReactor):
    pass


reactor = SelectReactorSubclass()
installReactor(reactor)


class NoRequestsSpider(scrapy.Spider):
    name = 'no_request'

    def start_requests(self):
        return []


process = CrawlerProcess(settings={
    "TWISTED_REACTOR": "twisted.internet.selectreactor.SelectReactor",
})

process.crawl(NoRequestsSpider)
process.start()
