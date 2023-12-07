import scrapy


class Spider1Spider(scrapy.Spider):
    name = "spider1"
    allowed_domains = ["test.com"]
    start_urls = ["https://www.naver.com/"]

    def parse(self, response):
        pass
