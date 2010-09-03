from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.item import BaseItem
from scrapy.utils import display
from scrapy.utils.spider import iterate_spider_output, create_spider_for_request
from scrapy.utils.url import is_url
from scrapy.exceptions import UsageError
from scrapy import log

class Command(ScrapyCommand):

    requires_project = True

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

    def pipeline_process(self, item, spider, opts):
        return item

    def run_callback(self, spider, response, callback, opts):
        cb = callback if callable(callback) else getattr(spider, callback, None)
        if not cb:
            log.msg('Cannot find callback %r in spider: %s' % (callback, spider.name))
            return (), ()

        items, requests = [], []
        for x in iterate_spider_output(cb(response)):
            if isinstance(x, BaseItem):
                items.append(x)
            elif isinstance(x, Request):
                requests.append(x)
        return items, requests

    def get_callback_from_rules(self, spider, response):
        if getattr(spider, 'rules', None):
            for rule in spider.rules:
                if rule.link_extractor.matches(response.url) and rule.callback:
                    return rule.callback
        else:
            log.msg("No CrawlSpider rules found in spider %r, please specify "
                "a callback to use for parsing" % spider.name, log.ERROR)

    def print_results(self, items, requests, cb_name, opts):
        if not opts.noitems:
            print "# Scraped Items - callback: %s" % cb_name, "-"*60
            display.pprint([dict(x) for x in items], colorize=not opts.nocolour)
        if not opts.nolinks:
            print "# Requests - callback: %s" % cb_name, "-"*68
            display.pprint(requests, colorize=not opts.nocolour)

    def get_spider(self, request, opts):
        if opts.spider:
            try:
                return self.crawler.spiders.create(opts.spider)
            except KeyError:
                log.msg('Unable to find spider: %s' % opts.spider, log.ERROR)
        else:
            spider = create_spider_for_request(self.crawler.spiders, request)
            if spider:
                return spider
            log.msg('Unable to find spider for: %s' % request, log.ERROR)

    def get_response_and_spider(self, url, opts):
        responses = [] # to collect downloaded responses
        request = Request(url, callback=responses.append)
        spider = self.get_spider(request, opts)
        if not spider:
            return None, None
        self.crawler.queue.append_request(request, spider)
        self.crawler.start()
        if not responses:
            log.msg('No response downloaded for: %s' % request, log.ERROR, \
                spider=spider)
            return None, None
        return responses[0], spider

    def run(self, args, opts):
        if not len(args) == 1 or not is_url(args[0]):
            raise UsageError()
        response, spider = self.get_response_and_spider(args[0], opts)
        if not response:
            return
        callback = None
        if opts.callback:
            callback = opts.callback
        elif opts.rules:
            callback = self.get_callback_from_rules(spider, response)
        items, requests = self.run_callback(spider, response, callback or 'parse', \
            opts)
        self.print_results(items, requests, callback, opts)

