from scrapy.spiders import Spider, ignore_spider


@ignore_spider
class IgnoredSpider(Spider):
    name = "ignored"


class SubclassSpider(IgnoredSpider):
    name = "subclass"
