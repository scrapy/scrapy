from scrapy.spider import BaseSpider

class Spider1(BaseSpider):
    name = "spider1"
    allowed_domains = ["scrapy1.org", "scrapy3.org"]
