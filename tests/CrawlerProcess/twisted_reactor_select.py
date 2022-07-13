import scrapy
from scrapy.crawler import CrawlerProcess


class SelectReactorSpider(scrapy.Spider):
    name = 'epoll_reactor'


process = CrawlerProcess(settings={
    "TWISTED_REACTOR": "twisted.internet.selectreactor.SelectReactor",
})
process.crawl(SelectReactorSpider)
process.start()
