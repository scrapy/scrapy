import scrapy


class QuotesSpider(scrapy.Spider):
    name = "quotes"

    def start_requests(self):
        urls = [
            'https://www.google.com/',
            'https://www.google.com/',
        ]
        for url in urls:
            yield scrapy.Request(url=url)
