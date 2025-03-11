from twisted.internet import selectreactor
from twisted.python import log

import scrapy
from scrapy.crawler import CrawlerProcess

selectreactor.install()


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    def start_requests(self):
        return []


process = CrawlerProcess(settings={})

d = process.crawl(NoRequestsSpider)
d.addErrback(log.err)
process.start()
