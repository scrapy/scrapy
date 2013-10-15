import re
import itertools
from w3lib.url import is_url

from scrapy.exceptions import UsageError
from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.utils.url import parse_url
from scrapy import signals, settings


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {"LOG_ENABLED": False}

    found = False

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
        headers = settings.default_settings.PROBE_REQUEST_HEADERS
        headers['Host'].append(parse_url(url).netloc)
        for key, value in settings.default_settings.DEFAULT_REQUEST_HEADERS.items():
            headers[key].append(value)

        sorted_headers = sorted(headers)
        combinations = [dict(zip(sorted_headers, prod)) 
                        for prod in itertools.product(*(headers[key]
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
