from scrapy.command import ScrapyCommand
from scrapy.fetcher import fetch
from scrapy.http import Request
from scrapy.item import ScrapedItem
from scrapy.spider import spiders
from scrapy.utils import display
from scrapy import log

class Command(ScrapyCommand):
    def syntax(self):
        return "[options] <url> <method>"

    def short_desc(self):
        return "Parse the URL with the given spider method and print the results"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--links", dest="links", action="store_true", help="show extracted links")
        parser.add_option("--noitems", dest="noitems", action="store_true", help="don't show scraped items")
        parser.add_option("--nocolour", dest="nocolour", action="store_true", help="avoid using pygments to colorize the output")

    def pipeline_process(self, item, opts):
        return item

    def run_method(self, response, method, args, opts):
        spider = spiders.fromurl(response.url)
        if not spider:
            log.msg('Couldnt find spider for url: %s' % response.url, level=log.ERROR)
            return (), ()

        items = []
        links = []
        if method:
            method_fcn = method if callable(method) else getattr(spider, method, None)
            if not method_fcn:
                log.msg('Couldnt find method %s in spider %s' % (method, spider.__name__))
                return (), ()

            result = method_fcn(response)
            links = [i for i in result if isinstance(i, Request)]
            items = [self.pipeline_process(i, opts) for i in result if isinstance(i, ScrapedItem)]
            for item in items:
                for key in item.__dict__.keys():
                    if key.startswith('_'):
                        item.__dict__.pop(key, None)

        return items, links

    def print_results(self, items, links, opts):
        display.nocolour = opts.nocolour
        if not opts.noitems:
            print "# Scraped Items", "-"*60
            display.pprint(list(items))

        if opts.links:
            print "# Links", "-"*68
            display.pprint(list(links))

    def run(self, args, opts):
        if len(args) < 2:
            print "A URL and method is required"
            return

        items = set()
        links = set()
        url, method = args[:2]
        for response in fetch([url]):
            ret_items, ret_links = self.run_method(response, method, args, opts)
            items = items.union(ret_items)
            links = links.union(ret_links)

        self.print_results(items, links, opts)

