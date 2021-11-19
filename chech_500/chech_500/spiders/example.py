# -*- coding: utf-8 -*-
import scrapy


class ExampleSpider(scrapy.Spider):
    name = 'example'
    start_urls = ['http://httpbin.org']

    def parse(self, response):
        yield response.follow(
            'http://httpbin.org/status/500',
            flags=['test_flag'],
            callback=self.parse,
        )
