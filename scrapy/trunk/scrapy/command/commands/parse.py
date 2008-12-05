from scrapy.command import ScrapyCommand
from scrapy.fetcher import fetch
from scrapy.http import Request
from scrapy.item import ScrapedItem
from scrapy.spider import spiders
from scrapy.utils import display
from scrapy import log

class Command(ScrapyCommand):
    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Parse the given URL and print the results"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--nolinks", dest="nolinks", action="store_true", help="don't show extracted links")
        parser.add_option("--noitems", dest="noitems", action="store_true", help="don't show scraped items")
        parser.add_option("--nocolour", dest="nocolour", action="store_true", help="avoid using pygments to colorize the output")
        parser.add_option("-r", "--rules", dest="rules", action="store_true", help="try to match and parse the url with the defined rules (if any)")
        parser.add_option("-c", "--callbacks", dest="callbacks", action="store", help="use the provided callback(s) for parsing the url (separated with commas)")

    def process_options(self, args, opts):
        self.callbacks = opts.callbacks.split(',') if opts.callbacks else []

    def pipeline_process(self, item, spider, opts):
        return item

    def run_callback(self, spider, response, callback, args, opts):
        spider = spiders.fromurl(response.url)
        if not spider:
            log.msg('Cannot find spider for url: %s' % response.url, level=log.ERROR)
            return (), ()

        if callback:
            callback_fcn = callback if callable(callback) else getattr(spider, callback, None)
            if not callback_fcn:
                log.msg('Cannot find callback %s in %s spider' % (callback, spider.domain_name))
                return (), ()

            result = callback_fcn(response)
            links = [i for i in result if isinstance(i, Request)]
            items = [self.pipeline_process(i, spider, opts) for i in result if isinstance(i, ScrapedItem)]
            return items, links

        return (), ()

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
        if not args:
            print "An URL is required"
            return

        ret_items, ret_links = [], []
        for response in fetch(args):
            spider = spiders.fromurl(response.url)
            if not spider:
                log.msg('Cannot find spider for "%s"' % response.url)
                continue

            if self.callbacks:
                items, links = [], []
                for callback in self.callbacks:
                    r_items, r_links = self.run_callback(spider, response, callback, args, opts)
                    items.extend(r_items)
                    links.extend(r_links)

            elif opts.rules:
                for rule in getattr(spider, 'rules', ()):
                    if rule.link_extractor.matches(response.url):
                        items, links = self.run_callback(spider, response, rule.callback, args, opts)
                        break
                else:
                    log.msg('No rules found for spider "%s", please specify a parsing callback' % spider.domain_name)
                    continue
            else:
                items, links = self.run_callback(spider, response, 'parse', args, opts)

            ret_items.extend(items)
            ret_links.extend(links)

        self.print_results(ret_items, ret_links, opts)

