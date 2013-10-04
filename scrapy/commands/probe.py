import re, itertools
from w3lib.url import is_url

from scrapy.exceptions import UsageError
from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy import signals, settings


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {"LOG_ENABLED": False}

    found = False
    headers = {
        #List of well known User-Agents
        "User-Agent": [
            "Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)",
            "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36" \
                " (KHTML, like Gecko) Chrome/29.0.1547.66 " \
                "Safari/537.36",
            "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) " \
                "Gecko/20100101 Firefox/23.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_4) " \
                "AppleWebKit/536.30.1 (KHTML, like Gecko) " \
                "Version/6.0.5 Safari/536.30.1",
            "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; " \
                "WOW64; Trident/6.0)",
            "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; " \
                "rv:1.8.1.6) Gecko/20070725 Firefox/2.0.0.6",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 6_1_3 like Mac OS X) AppleWebKit/536.26 " \
                "(KHTML, like Gecko) Version/6.0 Mobile/10B329 Safari/8536.25",
            "Mozilla/5.0 (Linux; Android 4.1.2; GT-I9100 Build/JZO54K) AppleWebKit/537.36 " \
                "(KHTML, like Gecko) Chrome/29.0.1547.72 Mobile Safari/537.36"
        ],
        #List of well known Accept media type
        "Accept": [
            "application/xml,application/xhtml+xml,text/html;q=0.9," \
                "text/plain;q=0.8,*/*;q=0.5",
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        ],
        #List of natural languages that are preferred
        "Accept-Language": [
            "en-US,en;q=0.8,pt;q=0.6,es;q=0.4,fr;q=0.2"
        ],
        #List of character sets are acceptable for the response
        "Accept-Charset": [
            "ISO-8859-1",
            "UTF-8",
            "*"
        ],
        "Cache-Control": [
            "no-cache"
        ],
        "Connection": [
            "keep-alive"
        ],
        "Host": [""]
    }

    FOUND_MESSAGE = "Found set of working headers:"
    NOT_FOUND_MESSAGE = "Set of working headers not found."

    def syntax(self):
        return "<url> <text>"

    def short_desc(self):
        return "Tries several combinations of HTTP headers"

    def long_desc(self):
        return "Tries several combinations of HTTP headers " \
            "and returns a set for which the text passed as argument is " \
            "found in the page content"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)

    def run(self, args, opts):
        if len(args) != 2 or not is_url(args[0]):
            raise UsageError()
        
        url = args[0]
        search_string = args[1]
        self._combine_HTTP_headers(url, search_string)

    def _engine_stopped(self):
        if not self.found:
            print self.NOT_FOUND_MESSAGE

    def _combine_HTTP_headers(self, url, search_string):
        """
        Builds combinations of HTTP headers, and checks if page content
        has the search string
        """
        
        for key, value in settings.default_settings.DEFAULT_REQUEST_HEADERS.items():
            self.headers[key].append(value)

        sorted_headers = sorted(self.headers)
        combinations = [dict(zip(sorted_headers, prod)) 
                        for prod in itertools.product(*(self.headers[key]
                                                      for key in sorted_headers))]

        cb = lambda x: self._verify_if_match(x, search_string)
        requests = [Request(url, headers=h, callback=cb, dont_filter=True)
                    for h in combinations]

        spider = BaseSpider('default')
        self.pcrawler = self.crawler_process.create_crawler()
        self.pcrawler.signals.connect(self._engine_stopped, signal=signals.engine_stopped)
        self.pcrawler.crawl(spider, requests)
        self.crawler_process.start()

    def _verify_if_match(self, response, search_string):
        if re.search(search_string, response.body) and not self.found:
            self.found = True
            print self.FOUND_MESSAGE
            print response.request.headers
            self.pcrawler.stop()
