
# *-* coding: utf-8 *-*

from scrapy.spider import Spider
from scrapy.selector import Selector
from scrapy.crawler import Crawler
from scrapy.http import Request
from scrapy import log, signals
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor

from datetime import datetime
import re

# variables
name_file = "output.txt"
keyword = ["feature film", "indie film", "film production", "independent film", "film casting", "movie casting",
           "extras casting", "film editor", "movie editor", "post production", "movie production", "line producer",
           "production manager", "editor", "colorist", "visual effects", "sound design", "VFX", "motion picture",
           "film sales", "film distribution", "film budget"]
added_email = []

# processing
keyword = list(map(lambda x: re.sub(' ', '+', x), keyword))
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
        print response.url
        sel = Selector(response)
        email = sel.re('(\w+@[a-zA-Z_]+?\.[a-zA-Z]{2,6})')[0]
        print email
        if email not in email_in_file and email not in added_email:
            file.write(email+'\n')
            added_email.append(email)

if __name__ == '__main__':
    options = {
        'CONCURRENT_ITEMS': 250,
        'USER_AGENT': 'Googlebot/2.1 (+http://www.google.com/bot.html)',
        'CONCURRENT_REQUESTS': 30,
        'DOWNLOAD_DELAY': 0.5,
        'COOKIES_ENABLED': False,
    }

    spider =Mandy()
    settings = get_project_settings()
    settings.overrides.update(options)
    crawler = Crawler(settings)
    crawler.signals.connect(reactor.stop, signal=signals.spider_closed)
    crawler.install()
    crawler.configure()
    crawler.crawl(spider)
    crawler.start()
    log.start(logfile="results.log", loglevel=log.DEBUG, crawler=crawler, logstdout=False)
    reactor.run()