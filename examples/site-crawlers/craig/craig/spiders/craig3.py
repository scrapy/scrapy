#!/usr/bin/python
# -*- coding: utf-8 -*-

from scrapy.spider import Spider
from scrapy.selector import Selector
from scrapy.crawler import Crawler
from scrapy.http import Request
from scrapy import signals
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor

from datetime import datetime
import re

keyword = ["feature film", "indie film", "film production", "independent film", "film casting", "movie casting",
           "extras casting", "film editor", "movie editor", "post production", "movie production", "line producer",
           "production manager", "editor", "colorist", "visual effects", "sound design", "VFX", "motion picture",
           "film sales", "film distribution", "film budget"]

options = {
        'CONCURRENT_ITEMS': 150,
        'USER_AGENT': "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/535.24 (KHTML, like Gecko) "
                      "Chrome/19.0.1055.1 Safari/535.24",
        'CONCURRENT_REQUESTS': 5,
        'SW_SAVE_BUFFER': 30,
        'DOWNLOAD_DELAY': 1.5,
        'COOKIES_ENABLED': False,
    }

""" Below is the current date. To change it to automatically check,
replace "Feb 28" value without the quotes "datetime.today().strftime('%b %d')" """

current_date = "Feb 28"  # datetime.today().strftime('%b %d')
keyword = list(map(lambda x: re.sub(' ', '+', x), keyword))
name_file = 'outfile.txt'
file_out = open(name_file, 'a', 0)
emails_current_session = []
emails_in_file = open(name_file, 'r').readlines()

class Craiglist(Spider):
    name = 'craiglist'
    allowed_domains = ["craigslist.org"]
    start_urls = ["http://www.craigslist.org/about/sites"]

    def parse(self, response):
        sel = Selector(response)
        links = sel.xpath('//*[@id="pagecontainer"]/section/div/div/ul/li/a/@href').extract()
        for link in links:
            for key in keyword:
                yield Request(url="{0}/search/ggg?zoomToPosting=&catAbb=ggg&query={1}&minAsk=&maxAsk="
                                  "&sort=rel&excats=".format(link, key), callback=self.parse_catalog)

    def parse_catalog(self, response):
        sel = Selector(response)
        count = sel.xpath('//*[@id="toc_rows"]/div[1]/div/span[2]/span[3]/span/text()').extract()
        if bool(count) and int(count[0]) <= 100:
            for i in range(1, int(count[0]) + 1):
                links = sel.xpath('//*[@id="toc_rows"]/div[2]/p[{0}]/span[2]/a/@href'.format(i)).extract()[0]
                date = sel.xpath('//*[@id="toc_rows"]/div[2]/p[{0}]/span[2]/span/text()'.format(i)).extract()[0]
                try:
                    if current_date == datetime.strptime(date, '%b %d').strftime('%b %d'):
                        num = links.split('/')[-1].split('.')[0]
                        site = links.split('/')[2]
                        link = "http://" + site + "/reply/" + num
                        yield Request(url=link, callback=self.parse_page)

                except (ValueError, UnicodeEncodeError):
                    yield Request(url="http://" + response.url.split('/')[2] + links, callback=self.parse_bad_date)

        elif bool(count) and int(count[0]) > 100:
            for count_page in range(0, int(count[0]), 100):
                if count_page == 0:
                    yield Request(url=response.url, callback=self.parse_links)
                if count_page > 0:
                    key = sel.xpath('//*[@id="query"]/@value').extract()[0]
                    link = response.url.split('/')[2]
                    yield Request(url="http://{0}/search/sss?s={1}&catAbb=sss&query={2}&sort=rel".format
                        (link, count_page, key), callback=self.parse_links)

    def parse_links(self, response):
        sel = Selector(response)
        count = sel.xpath('//*[@id="toc_rows"]/div[1]/div/span[2]/span[1]/text()').re('(\d+)')
        count = int(count[1]) - int(count[0]) + 2
        for i in range(1, count):
                links = sel.xpath('//*[@id="toc_rows"]/div[2]/p[{0}]/span[2]/a/@href'.format(i)).extract()[0]
                date = sel.xpath('//*[@id="toc_rows"]/div[2]/p[{0}]/span[2]/span/text()'.format(i)).extract()[0]
                if current_date == datetime.strptime(date, '%b %d').strftime('%b %d'):
                    num = links.split('/')[-1].split('.')[0]
                    site = response.url.split('/')[2]
                    link = "http://" + site + "/reply/" + num
                    yield Request(url=link, callback=self.parse_page)

    def parse_bad_date(self, response):
        sel = Selector(response)
        date = sel.xpath('//*[@id="pagecontainer"]/section/section[2]/div[2]/p[3]/time/text()')\
            .re("(\d{4}\-\d{1,2}\-\d{1,2})")
        if not bool(date):
            date = sel.xpath('//*[@id="pagecontainer"]/section/section[2]/div[2]/p[2]/time/text()')\
                .re("(\d{4}\-\d{1,2}\-\d{1,2})")
        if current_date == datetime.strptime(date[0], '%Y-%m-%d').strftime('%b %d'):
            print response.url
            yield Request(url=response.url, callback=self.parse_page)

    def parse_page(self, response):
        sel = Selector(response)
        email = sel.xpath('//div/ul//input/@value').extract()
        if bool(email):
            email = email[0]
            if email not in emails_in_file and email not in emails_current_session:
                file_out.write("{}\n".format(email))
                emails_current_session.append(email)
                print "Email {0} added to file".format(email)
            else:
                print "Email {0} present in file".format(email)

if __name__ == '__main__':
    spider = Craiglist()
    settings = get_project_settings()
    settings.overrides.update(options)
    crawler = Crawler(settings)
    crawler.signals.connect(reactor.stop, signal=signals.spider_closed)
    crawler.install()
    crawler.configure()
    crawler.crawl(spider)
    crawler.start()
    reactor.run()