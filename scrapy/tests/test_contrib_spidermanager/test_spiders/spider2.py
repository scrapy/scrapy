from scrapy.spider import BaseSpider

class Spider2(BaseSpider):
    name = "spider2"
    allowed_domains = ["scrapy2.org", "scrapy3.org"]
