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
        parser.add_option("--nolinks", dest="nolinks", action="store_true", help="don't show extracted links")
        parser.add_option("--noitems", dest="noitems", action="store_true", help="don't show scraped items")
        parser.add_option("--nocolour", dest="nocolour", action="store_true", help="avoid using pygments to colorize the output")
        parser.add_option("--matches", dest="matches", action="store_true", help="avoid using pygments to colorize the output")

    def pipeline_process(self, item, spider, opts):
        return item

    def run_method(self, spider, response, method, args, opts):
        spider = spiders.fromurl(response.url)
        if not spider:
            log.msg('Couldnt find spider for url: %s' % response.url, level=log.ERROR)
            return (), ()

        items = []
        links = []
        if method:
            method_fcn = method if callable(method) else getattr(spider, method, None)
            if not method_fcn:
                log.msg('Couldnt find method %s in %s spider' % (method, spider.domain_name))
                return (), ()

            result = method_fcn(response)
            links = [i for i in result if isinstance(i, Request)]
            items = [self.pipeline_process(i, spider, opts) for i in result if isinstance(i, ScrapedItem)]

        return items, links

    def print_results(self, items, links, opts):
        display.nocolour = opts.nocolour
        if not opts.noitems:
            for item in items:
                for key in item.__dict__.keys():
                   if key.startswith('_'):
                       item.__dict__.pop(key, None)
            print "# Scraped Items", "-"*60
            display.pprint(list(items))

        if not opts.nolinks:
            print "# Links", "-"*68
            display.pprint(list(links))

    def run(self, args, opts):
        if opts.matches:
            url = args[0]
            method = None            
        else:
            if len(args) < 2:
                print "A URL and method is required"
                return
            else:
                url, method = args[:2]

        items = set()
        links = set()
        for response in fetch([url]):
            spider = spiders.fromurl(response.url)
            if not spider:
                log.msg('Couldnt find spider for "%s"' % response.url)
                continue

            if method:
                ret_items, ret_links = self.run_method(spider, response, method, args, opts)
                items = items.union(ret_items)
                links = links.union(ret_links)
            else:
                if hasattr(spider, 'rules'):
                    for rule in spider.rules:
                        if rule.link_extractor.matches(response.url):
                            ret_items, ret_links = self.run_method(spider, response, rule.callback, args, opts)
                            items = items.union(ret_items)
                            links = links.union(ret_links)
                else:
                    log.msg('No rules found for spider "%s", please specify a parsing method' % spider.domain_name)
                    continue

        self.print_results(items, links, opts)

