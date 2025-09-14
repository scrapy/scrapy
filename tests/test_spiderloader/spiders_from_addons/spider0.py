from scrapy.spiders import Spider


class SpiderFromAddon(Spider):
    name = "spider_from_addon"
    allowed_domains = ["scrapy1.org", "scrapy3.org"]
