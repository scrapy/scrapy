from scrapy.spiders import Spider, ignore_spider


@ignore_spider
class Spider0(Spider):
    allowed_domains = ["scrapy1.org", "scrapy3.org"]
