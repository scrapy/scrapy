#!/usr/bin/python
# -*- coding: utf-8 -*-

from scrapy.spider import Spider
from scrapy.selector import Selector
from scrapy.http import Request

from my_settings import name_file, keyword, test_mode, difference_days
from datetime import datetime, timedelta
import re

print "Run spider ProductionHub"

if test_mode:
    current_date = (datetime.today() - timedelta(days=difference_days)).strftime('%m.%d.%Y')
else:
    current_date = datetime.today().strftime('%m.%d.%Y')

current_session_emails = []
file = open(name_file, 'a')
email_in_file = open(name_file, 'r').readlines()

# processing
keyword = list(map(lambda x: re.sub(' ', '%20', x), keyword))


class ProductionHub(Spider):
    name = 'productionhub'
    allowed_domains = ["productionhub.com"]
    start_urls = ["http://www.productionhub.com/jobs/search?q={}".format(key)
                  for key in keyword]

    def parse(self, response):
        sel = Selector(response)
        count = sel.xpath('//*[@id="main-content"]/div[3]/div/text()').re('\w+')
        if bool(count):
            count = count[-1]
            for num_page in xrange(1, int(count) + 1):
                yield Request(url=response.url+'&page={}'.format(str(num_page)), callback=self.parse_count_page)

    def parse_count_page(self, response):
        sel = Selector(response)
        links = sel.xpath('//*[@id="main-content"]/div/div/div/h4/a/@href').extract()
        date = sel.xpath('//*[@id="main-content"]/div[2]/div/div/div/footer/span/text()').re('(\d{1,2}\/\d{1,2}\/\d{4})')
        dic = dict(zip(links, date))
        for key in dic.keys():
            if datetime.strptime(dic[key], '%m/%d/%Y').strftime('%m.%d.%Y') == current_date:
                yield Request(url='http://www.productionhub.com'+key, callback=self.parse_page)

    def parse_page(self, response):
        sel = Selector(response)
        emails = sel.re('(\w+@[a-zA-Z_]+?\.[a-zA-Z]{2,6})')
        emails = list(filter(lambda x: x != 'press@productionhub.com', emails))
        if bool(emails):
            for email in emails:
                if email + "\n" not in email_in_file and email not in current_session_emails:
                    file.write(email+'\n')
                    current_session_emails.append(email)
                    print 'Spider: ProductionHub. Email {0} added to file'.format(email)
                else:
                    print 'Spider: ProductionHub. Email {0} already in the file'.format(email)