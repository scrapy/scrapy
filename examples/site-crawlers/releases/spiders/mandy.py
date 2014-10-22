#!/usr/bin/python
# -*- coding: utf-8 -*-

from scrapy.spider import Spider
from scrapy.selector import Selector
from scrapy.http import Request

from my_settings import name_file, keyword, test_mode, difference_days
from datetime import datetime, timedelta
import re

print "Run spider Mandy"

added_email = []
keyword = list(map(lambda x: re.sub(' ', '+', x), keyword))

if test_mode:
    current_date = (datetime.today() - timedelta(days=difference_days)).strftime('%d-%b-%Y')
else:
    current_date = datetime.today().strftime('%d-%b-%Y')

file = open(name_file, 'a')
email_in_file = open(name_file, 'r').readlines()

class Mandy(Spider):
    name = 'mandy'
    allowed_domains = ["mandy.com"]
    start_urls = ["http://mandy.com/1/search.cfm?fs=1&place=wld&city=&what={}&where=Worldwide".format(key)
                  for key in keyword]

    def parse(self, response):
        sel = Selector(response)
        date = sel.xpath('//*[@id="resultswrapper"]/section/div/div/div/div/span/text()').extract()
        link = sel.xpath('//*[@id="resultswrapper"]/section/div/div/div/div/a/@href').extract()
        date = list(map(lambda x: re.findall('\w+:\D([A-Za-z0-9-]+)', x)[0], date))
        dic = dict(zip(link, date))
        for key in dic.keys():
            if dic[key] == current_date:
                yield Request(url='http://mandy.com'+key, callback=self.parse_page)


    def parse_page(self, response):
        sel = Selector(response)
        email = sel.re('(\w+@[a-zA-Z_]+?\.[a-zA-Z]{2,6})')
        if bool(email):
            email = email[0]
            if email + "\n" not in email_in_file and email not in added_email:
                file.write(email+'\n')
                added_email.append(email)
                print "Spider: Mandy. Email {0} added to file".format(email)
            else:
                print "Spider: Mandy. Email {0} already in the file".format(email)