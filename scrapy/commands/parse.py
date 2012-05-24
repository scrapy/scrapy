from w3lib.url import is_url
from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.item import BaseItem
from scrapy.utils import display
from scrapy.utils.spider import iterate_spider_output, create_spider_for_request
from scrapy.exceptions import UsageError
from scrapy import log

class Command(ScrapyCommand):

    requires_project = True

    spider = None
    items = []
    requests = []
    
    first_response = None

    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Parse URL (using its spider) and print the results"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--spider", dest="spider", default=None, \
            help="use this spider without looking for one")
        parser.add_option("--nolinks", dest="nolinks", action="store_true", \
            help="don't show links to follow (extracted requests)")
        parser.add_option("--noitems", dest="noitems", action="store_true", \
            help="don't show scraped items")
        parser.add_option("--nocolour", dest="nocolour", action="store_true", \
            help="avoid using pygments to colorize the output")
        parser.add_option("-r", "--rules", dest="rules", action="store_true", \
            help="use CrawlSpider rules to discover the callback")
        parser.add_option("-c", "--callback", dest="callback", \
            help="use this callback for parsing, instead looking for a callback")
        parser.add_option("-d", "--depth", dest="depth", type="int", default=1, \
            help="maximum depth for parsing requests [default: %default]")
        # parser.add_option("-v", "--verbose", dest="verbose", action="store_true", \
        #     help="print each depth level one by one")

    def run_callback(self, response, cb):
        items, requests = [], []

        for x in iterate_spider_output(cb(response)):
            if isinstance(x, BaseItem):
                items.append(x)
            elif isinstance(x, Request):
                requests.append(x)
        return items, requests

    def get_callback_from_rules(self, response):
        if getattr(self.spider, 'rules', None):
            for rule in self.spider.rules:
                if rule.link_extractor.matches(response.url) and rule.callback:
                    return rule.callback
        else:
            log.msg("No CrawlSpider rules found in spider %r, please specify "
                "a callback to use for parsing" % self.spider.name, log.ERROR)

    def print_results(self, opts):
        if not opts.noitems:
            print "# Scraped Items ", "-"*60
            display.pprint([dict(x) for x in self.items], colorize=not opts.nocolour)
        if not opts.nolinks:
            print "# Requests ", "-"*65
            display.pprint(self.requests, colorize=not opts.nocolour)

    def set_spider(self, url, opts):
        if opts.spider:
            try:
                self.spider = self.crawler.spiders.create(opts.spider)
            except KeyError:
                log.msg('Unable to find spider: %s' % opts.spider, log.ERROR)
        else:
            self.spider = create_spider_for_request(self.crawler.spiders, url)
            if not self.spider:
                log.msg('Unable to find spider for: %s' % request, log.ERROR)

    def start_parsing(self, url, opts):
        request = Request(url, opts.callback)
        request = self.prepare_request(request, opts)

        self.crawler.crawl(self.spider, [request])
        self.crawler.start()

        if not self.first_response:
            log.msg('No response downloaded for: %s' % request, log.ERROR, \
                spider=self.spider)

    def prepare_request(self, request, opts):
        def callback(response):
            # memorize first request
            if not self.first_response:
                self.first_response = response

            # determine real callback
            cb = response.meta['_callback']
            if not cb:
                if opts.rules and self.first_response == response:
                    cb = self.get_callback_from_rules(response)
                else:
                    cb = 'parse'

            cb = cb if callable(cb) else getattr(self.spider, cb, None)
            if not cb:
                log.msg('Cannot find callback %r in spider: %s' % (callback, spider.name))

            # parse items and requests
            items, requests = self.run_callback(response, cb)
            self.items += items

            depth = response.meta['_depth']
            if depth < opts.depth:
                for req in requests:
                    req.meta['_depth'] = depth + 1
                    req.meta['_callback'] = req.callback
                    req.callback = callback
                return requests
            else:
                self.requests += requests

        request.meta['_depth'] = 1
        request.meta['_callback'] = request.callback
        request.callback = callback
        return request

    def run(self, args, opts):
        # parse arguments
        if not len(args) == 1 or not is_url(args[0]):
            raise UsageError()
        else:
            url = args[0]

        # prepare spider
        self.set_spider(url, opts)

        if self.spider and opts.depth > 0:
            self.start_parsing(url, opts)
            self.print_results(opts)
