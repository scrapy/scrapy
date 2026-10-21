from scrapy.spiders import Spider


class Spider0(Spider, abstract=True):
    allowed_domains = ["scrapy1.org", "scrapy3.org"]
