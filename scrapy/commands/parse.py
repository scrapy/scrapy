from scrapy.command import ScrapyCommand
from scrapy.project import crawler
from scrapy.http import Request
from scrapy.item import BaseItem
from scrapy.spider import spiders
from scrapy.utils import display
from scrapy.utils.spider import iterate_spider_output
from scrapy.utils.url import is_url
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
            help="always use this spider")
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
        if callback:
            callback_fcn = callback if callable(callback) else getattr(spider, callback, None)
            if not callback_fcn:
                log.msg('Cannot find callback %s in %s spider' % (callback, spider.name))
                return (), ()

            result = iterate_spider_output(callback_fcn(response))
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
        if not len(args) == 1 or not is_url(args[0]):
            return False

        responses = [] # to collect downloaded responses
        request = Request(args[0], callback=responses.append)

        if opts.spider:
            try:
                spider = spiders.create(opts.spider)
            except KeyError:
                log.msg('Unable to find spider: %s' % opts.spider, log.ERROR)
                return
        else:
            spider = spiders.create_for_request(request)
            if spider is None:
                log.msg('Unable to find spider for URL: %s' % args[0], log.ERROR)
                return

        crawler.configure()
        crawler.queue.append_request(request, spider)
        crawler.start()

        if not responses:
            log.msg('No response returned', log.ERROR, spider=spider)
            return

        # now process response
        #   - if callbacks defined then call each one print results
        #   - if --rules option given search for matching spider's rule
        #   - default print result using default 'parse' spider's callback
        response = responses[0]

        if self.callbacks:
            # apply each callback
            for callback in self.callbacks:
                items, links = self.run_callback(spider, response,
                                                    callback, args, opts)
                self.print_results(items, links, callback, opts)
        elif opts.rules:
            # search for matching spider's rule
            if hasattr(spider, 'rules') and spider.rules:
                items, links = [], []
                for rule in spider.rules:
                    if rule.link_extractor.matches(response.url) \
                        and rule.callback:

                        items, links = self.run_callback(spider,
                                            response, rule.callback,
                                            args, opts)
                        self.print_results(items, links,
                                            rule.callback, opts)
                        # first-match rule breaks rules loop
                        break
            else:
                log.msg('No rules found for spider "%s", ' \
                        'please specify a callback for parsing' \
                        % spider.name, log.ERROR)
        else:
            # default callback 'parse'
            items, links = self.run_callback(spider, response,
                                                'parse', args, opts)
            self.print_results(items, links, 'parse', opts)

