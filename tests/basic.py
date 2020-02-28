import scrapy
from scrapy.crawler import CrawlerProcess
from ..items import BasicItem

class MySpider(scrapy.Spider):
    name = "basic"
    allowed_domains = ["web"]
    start_urls = ['https://www.rd.com/funny-stuff/short-jokes/']

    def parse(self, response):
        item =  BasicItem()

        title = response.css('.listicle-h2').extract()
        item['title']=title

        yield item
