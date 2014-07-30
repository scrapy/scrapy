from scrapy.spider import Spider

class Spider4(Spider):
    name = "spider4"

    @classmethod
    def from_crawler(cls, crawler, **kwargs):
        o = cls(**kwargs)
        o.crawler = crawler
        return o
