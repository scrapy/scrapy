import sys
import time
import subprocess
from urllib.parse import urlencode

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.linkextractors import LinkExtractor


class Command(ScrapyCommand):

    default_settings = {
        'LOG_LEVEL': 'INFO',
        'LOGSTATS_INTERVAL': 1,
        'CLOSESPIDER_TIMEOUT': 10,
    }

    def short_desc(self):
        return "Run quick benchmark test"

    def run(self, args, opts):
        with _BenchServer():
            self.crawler_process.crawl(_BenchSpider, total=100000)
            self.crawler_process.start()


class _BenchServer:

    def __enter__(self):
        from scrapy.utils.test import get_testenv
        pargs = [sys.executable, '-u', '-m', 'scrapy.utils.benchserver']
        self.proc = subprocess.Popen(pargs, stdout=subprocess.PIPE,
                                     env=get_testenv())
        self.proc.stdout.readline()

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)


class _BenchSpider(scrapy.Spider):
    """A spider that follows all links"""
    name = 'follow'
    total = 10000
    show = 20
    baseurl = 'http://localhost:8998'
    link_extractor = LinkExtractor()

    def start_requests(self):
        qargs = {'total': self.total, 'show': self.show}
        url = f'{self.baseurl}?{urlencode(qargs, doseq=1)}'
        return [scrapy.Request(url, dont_filter=True)]

    def parse(self, response):
        for link in self.link_extractor.extract_links(response):
            yield scrapy.Request(link.url, callback=self.parse)
