from __future__ import print_function
from w3lib.url import is_url
from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.item import BaseItem
from scrapy.utils import display
from scrapy.utils.conf import arglist_to_dict
from scrapy.utils.spider import iterate_spider_output, create_spider_for_request
from scrapy.exceptions import UsageError
from scrapy import log

class Command(ScrapyCommand):

    requires_project = True

    spider = None
    items = {}
    requests = {}

    first_response = None

    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Parse URL (using its spider) and print the results"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--spider", dest="spider", default=None, \
            help="use this spider without looking for one")
        parser.add_option("-a", dest="spargs", action="append", default=[], metavar="NAME=VALUE", \
            help="set spider argument (may be repeated)")
        parser.add_option("--pipelines", action="store_true", \
            help="process items through pipelines")
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
        parser.add_option("-v", "--verbose", dest="verbose", action="store_true", \
            help="print each depth level one by one")


    @property
    def max_level(self):
        levels = self.items.keys() + self.requests.keys()
        if levels: return max(levels)
        else: return 0

    def add_items(self, lvl, new_items):
        old_items = self.items.get(lvl, [])
        self.items[lvl] = old_items + new_items

    def add_requests(self, lvl, new_reqs):
        old_reqs = self.requests.get(lvl, [])
        self.requests[lvl] = old_reqs + new_reqs

    def print_items(self, lvl=None, colour=True):
        if lvl is None:
            items = [item for lst in self.items.values() for item in lst]
        else:
            items = self.items.get(lvl, [])

        print("# Scraped Items ", "-"*60)
        display.pprint([dict(x) for x in items], colorize=colour)

    def print_requests(self, lvl=None, colour=True):
        if lvl is None:
            levels = self.requests.keys()
            if levels:
                requests = self.requests[max(levels)]
            else:
                requests = []
        else:
            requests = self.requests.get(lvl, [])

        print("# Requests ", "-"*65)
        display.pprint(requests, colorize=colour)

    def print_results(self, opts):
        colour = not opts.nocolour

        if opts.verbose:
            for level in xrange(1, self.max_level+1):
                print('\n>>> DEPTH LEVEL: %s <<<' % level)
                if not opts.noitems:
                    self.print_items(level, colour)
                if not opts.nolinks:
                    self.print_requests(level, colour)
        else:
            print('\n>>> STATUS DEPTH LEVEL %s <<<' % self.max_level)
            if not opts.noitems:
                self.print_items(colour=colour)
            if not opts.nolinks:
                self.print_requests(colour=colour)


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
            log.msg(format='No CrawlSpider rules found in spider %(spider)r, '
                           'please specify a callback to use for parsing',
                    level=log.ERROR, spider=self.spider.name)

    def set_spider(self, url, opts):
        if opts.spider:
            try:
                self.spider = self.pcrawler.spiders.create(opts.spider, **opts.spargs)
            except KeyError:
                log.msg(format='Unable to find spider: %(spider)s',
                        level=log.ERROR, spider=opts.spider)
        else:
            self.spider = create_spider_for_request(self.pcrawler.spiders, Request(url), **opts.spargs)
            if not self.spider:
                log.msg(format='Unable to find spider for: %(url)s',
                        level=log.ERROR, url=url)

    def start_parsing(self, url, opts):
        request = Request(url, opts.callback)
        request = self.prepare_request(request, opts)

        self.pcrawler.crawl(self.spider, [request])
        self.crawler_process.start()

        if not self.first_response:
            log.msg(format='No response downloaded for: %(request)s',
                    level=log.ERROR, request=request)

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

            if not callable(cb):
                cb_method = getattr(self.spider, cb, None)
                if callable(cb_method):
                    cb = cb_method
                else:
                    log.msg(format='Cannot find callback %(callback)r in spider: %(spider)s',
                            callback=callback, spider=self.spider.name, level=log.ERROR)
                    return

            # parse items and requests
            depth = response.meta['_depth']

            items, requests = self.run_callback(response, cb)
            if opts.pipelines:
                itemproc = self.pcrawler.engine.scraper.itemproc
                for item in items:
                    itemproc.process_item(item, self.spider)
            self.add_items(depth, items)
            self.add_requests(depth, requests)

            if depth < opts.depth:
                for req in requests:
                    req.meta['_depth'] = depth + 1
                    req.meta['_callback'] = req.callback
                    req.callback = callback
                return requests

        request.meta['_depth'] = 1
        request.meta['_callback'] = request.callback
        request.callback = callback
        return request

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError("Invalid -a value, use -a NAME=VALUE", print_help=False)

    def run(self, args, opts):
        # parse arguments
        if not len(args) == 1 or not is_url(args[0]):
            raise UsageError()
        else:
            url = args[0]

        # prepare spider
        self.pcrawler = self.crawler_process.create_crawler()
        self.set_spider(url, opts)

        if self.spider and opts.depth > 0:
            self.start_parsing(url, opts)
            self.print_results(opts)
