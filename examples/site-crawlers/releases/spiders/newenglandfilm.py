#!/usr/bin/python
# -*- coding: utf-8 -*-

from scrapy.spider import Spider
from scrapy.selector import Selector

from my_settings import name_file, test_mode, difference_days
from datetime import datetime, timedelta

print "Run spider NewenglandFilm"

file_output = open(name_file, 'a')
email_current_session = []
email_in_file = open(name_file, 'r').readlines()

if test_mode:
    current_date = (datetime.today() - timedelta(days=difference_days)).strftime('%m/%d/%Y')
else:
    current_date = datetime.today().strftime('%m/%d/%Y')

class NewenglandFilm(Spider):
    name = 'newenglandfilm'
    allowed_domains = ["newenglandfilm.com"]
    start_urls = ["http://newenglandfilm.com/jobs.htm"]

    def parse(self, response):
        sel = Selector(response)
        for num_div in xrange(1, 31):
            date = sel.xpath('//*[@id="mainContent"]/div[{0}]/span/text()'.format(str(num_div))).re('(\d{1,2}\/\d{1,2}\/\d{4})')[0]
            email = sel.xpath('//*[@id="mainContent"]/div[{0}]/div/text()'.format(str(num_div))).re('(\w+@[a-zA-Z0-9_]+?\.[a-zA-Z]{2,6})')
            if current_date == date:
                for address in email:
                    if address + "\n" not in email_in_file and address not in email_current_session:
                        file_output.write(address + "\n")
                        email_current_session.append(address)
                        print "Spider: NewenglandFilm. Email {0} added to file".format(address)
                    else:
                        print "Spider: NewenglandFilm. Email {0} already in the file".format(address)