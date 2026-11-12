from scrapy.spiders import Spider


class IgnoredSpider(Spider, abstract=True):
    name = "ignored"


class SubclassSpider(IgnoredSpider):
    name = "subclass"
