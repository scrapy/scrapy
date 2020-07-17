import scrapy
from scrapy.crawler import CrawlerProcess


class PollReactorSpider(scrapy.Spider):
    name = 'poll_reactor'


process = CrawlerProcess(settings={
    "TWISTED_REACTOR": "twisted.internet.pollreactor.PollReactor",
})
process.crawl(PollReactorSpider)
process.start()
