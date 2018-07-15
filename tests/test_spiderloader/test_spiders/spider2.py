from scrapy.spiders import Spider

class Spider2(Spider):
    name = "spider2"
    allowed_domains = ["scrapy2.org", "scrapy3.org"]
