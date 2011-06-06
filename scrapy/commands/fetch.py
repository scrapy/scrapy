from w3lib.url import is_url

from scrapy import log
from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.exceptions import UsageError

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
                print '%s %s: %s' % (prefix, key, value)

    def _print_response(self, response, opts):
        if opts.headers:
            self._print_headers(response.request.headers, '>')
            print '>'
            self._print_headers(response.headers, '<')
        else:
            print response.body

    def run(self, args, opts):
        if len(args) != 1 or not is_url(args[0]):
            raise UsageError()
        cb = lambda x: self._print_response(x, opts)
        request = Request(args[0], callback=cb, dont_filter=True)
        request.meta['handle_httpstatus_all'] = True

        spider = None
        if opts.spider:
            try:
                spider = self.crawler.spiders.create(opts.spider)
            except KeyError:
                log.msg("Could not find spider: %s" % opts.spider, log.ERROR)

        self.crawler.queue.append_request(request, spider, \
            default_spider=BaseSpider('default'))
        self.crawler.start()

