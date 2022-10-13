import scrapy
from scrapy.crawler import CrawlerProcess
from twisted.internet import selectreactor
selectreactor.install()


class NoRequestsSpider(scrapy.Spider):
    name = 'no_request'

    def start_requests(self):
        return []


process = CrawlerProcess(settings={
    "TWISTED_REACTOR": "twisted.internet.selectreactor.SelectReactor",
})

process.crawl(NoRequestsSpider)
process.start()
