
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

current_session_emails = []
current_date = datetime.today().strftime('%m.%d.%Y')
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
                if email not in email_in_file and email not in current_session_emails:
                    file.write(email+'\n')
                    current_session_emails.append(email)

if __name__ == '__main__':
    options = {
        'CONCURRENT_ITEMS': 250,
        'USER_AGENT': 'Googlebot/2.1 (+http://www.google.com/bot.html)',
        'CONCURRENT_REQUESTS': 30,
        'DOWNLOAD_DELAY': 0.5,
        'COOKIES_ENABLED': False,
    }

    spider = ProductionHub()
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