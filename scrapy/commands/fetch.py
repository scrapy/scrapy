from __future__ import print_function
import sys, six
from w3lib.url import is_url

from scrapy.commands import ScrapyCommand
from scrapy.http import Request
from scrapy.exceptions import UsageError
from scrapy.utils.spider import spidercls_for_request, DefaultSpider

class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Fetch a URL using the Scrapy downloader"

    def long_desc(self):
        return "Fetch a URL using the Scrapy downloader and print its content " \
            "to stdout. You may want to use --nolog to disable logging"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--spider", dest="spider",
            help="use this spider")
        parser.add_option("--headers", dest="headers", action="store_true", \
            help="print response HTTP headers instead of body")

    def _print_headers(self, headers, prefix):
        for key, values in headers.items():
            for value in values:
                self._print_bytes(prefix + b' ' + key + b': ' + value)

    def _print_response(self, response, opts):
        if opts.headers:
            self._print_headers(response.request.headers, b'>')
            print('>')
            self._print_headers(response.headers, b'<')
        else:
            self._print_bytes(response.body)

    def _print_bytes(self, bytes_):
        bytes_writer = sys.stdout if six.PY2 else sys.stdout.buffer
        bytes_writer.write(bytes_ + b'\n')

    def run(self, args, opts):
        if len(args) != 1 or not is_url(args[0]):
            raise UsageError()
        cb = lambda x: self._print_response(x, opts)
        request = Request(args[0], callback=cb, dont_filter=True)
        request.meta['handle_httpstatus_all'] = True

        spidercls = DefaultSpider
        spider_loader = self.crawler_process.spider_loader
        if opts.spider:
            spidercls = spider_loader.load(opts.spider)
        else:
            spidercls = spidercls_for_request(spider_loader, request, spidercls)
        self.crawler_process.crawl(spidercls, start_requests=lambda: [request])
        self.crawler_process.start()
