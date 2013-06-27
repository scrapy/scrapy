from scrapy.spider import BaseSpider

class Spider4(BaseSpider):
    name = "spider4"

    @classmethod
    def from_crawler(cls, crawler, **kwargs):
        o = cls(**kwargs)
        o.crawler = crawler
        return o
