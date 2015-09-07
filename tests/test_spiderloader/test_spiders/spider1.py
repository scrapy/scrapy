from scrapy.spiders import Spider

class Spider1(Spider):
    name = "spider1"
    allowed_domains = ["scrapy1.org", "scrapy3.org"]
