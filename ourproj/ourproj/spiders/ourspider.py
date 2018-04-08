# -*- coding: utf-8 -*-
import scrapy


class OurspiderSpider(scrapy.Spider):
    name = 'ourspider'
    allowed_domains = ['http://whatismyv6.com/']

    def start_requests(self):
        yield scrapy.Request('http://whatismyv6.com/', meta={'bindaddress': ('1234:5678:111::0a', 0)})

    def parse(self, response):
        pass
