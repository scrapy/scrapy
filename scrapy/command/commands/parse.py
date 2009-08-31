from scrapy.command import ScrapyCommand
from scrapy.fetcher import fetch
from scrapy.http import Request
from scrapy.item import BaseItem
from scrapy.spider import spiders
from scrapy.utils import display
from scrapy import log

class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Parse the given URL (using the spider) and print the results"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--nolinks", dest="nolinks", action="store_true", \
            help="don't show extracted links")
        parser.add_option("--noitems", dest="noitems", action="store_true", \
            help="don't show scraped items")
        parser.add_option("--nocolour", dest="nocolour", action="store_true", \
            help="avoid using pygments to colorize the output")
        parser.add_option("-r", "--rules", dest="rules", action="store_true", \
            help="try to match and parse the url with the defined rules (if any)")
        parser.add_option("-c", "--callbacks", dest="callbacks", action="store", \
            help="use the provided callback(s) for parsing the url (separated with commas)")

    def process_options(self, args, opts):
        super(Command, self).process_options(args, opts)
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
            items = [self.pipeline_process(i, spider, opts) for i in result if \
                     isinstance(i, BaseItem)]
            return items, links

        return (), ()

    def print_results(self, items, links, cb_name, opts):
        display.nocolour = opts.nocolour
        if not opts.noitems:
            for item in items:
                for key in item.__dict__.keys():
                    if key.startswith('_'):
                        item.__dict__.pop(key, None)
            print "# Scraped Items - callback: %s" % cb_name, "-"*60
            display.pprint(list(items))

        if not opts.nolinks:
            print "# Links - callback: %s" % cb_name, "-"*68
            display.pprint(list(links))

    def run(self, args, opts):
        if not args:
            print "An URL is required"
            return

        for response in fetch(args):
            spider = spiders.fromurl(response.url)
            if not spider:
                log.msg('Cannot find spider for "%s"' % response.url)
                continue

            if self.callbacks:
                for callback in self.callbacks:
                    items, links = self.run_callback(spider, response, callback, args, opts)
                    self.print_results(items, links, callback, opts)

            elif opts.rules:
                rules = getattr(spider, 'rules', None)
                if rules:
                    items, links = [], []
                    for rule in rules:
                        if rule.callback and rule.link_extractor.matches(response.url):
                            items, links = self.run_callback(spider, response, rule.callback, args, opts)
                            self.print_results(items, links, rule.callback, opts)
                            break
                else:
                    log.msg('No rules found for spider "%s", please specify a callback for parsing' \
                        % spider.domain_name)
                    continue

            else:
                items, links = self.run_callback(spider, response, 'parse', args, opts)
                self.print_results(items, links, 'parse', opts)

