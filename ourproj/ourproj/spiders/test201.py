# -*- coding: utf-8 -*-
import scrapy


class Test201Spider(scrapy.Spider):
    name = 'test201'
    allowed_domains = ['jsonplaceholder.typicode.com']
    start_urls = ['http://jsonplaceholder.typicode.com/posts/']

    custom_settings = {
        'LOG_FILE': '/tmp/example.log',
    }

    def parse(self, response):
        return [FormRequest(url='http://jsonplaceholder.typicode.com/posts',
        					formdata={'title':'testtitle', 'body':'testbody'},
        					callback=self.after_post,
        					dont_filter=True)]

    def after_post(self, response):
    	print ("Made the post request successfully")
