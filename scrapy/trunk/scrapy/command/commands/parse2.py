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
        parser.add_option("--nolinks", dest="nolinks", action="store_true", help="show extracted links")
        parser.add_option("--noitems", dest="noitems", action="store_true", help="don't show scraped items")
        parser.add_option("--nocolour", dest="nocolour", action="store_true", help="avoid using pygments to colorize the output")

    def pipeline_process(self, item, opts):
        return item

    def run(self, args, opts):
        if len(args) != 2:
            print "A URL and method is required"
            return

        url, method = args
        responses = fetch([url])
        for response in responses:
            spider = spiders.fromurl(response.url)
            if spider:
                method = getattr(spider, method)
                result = method(response)

                links = [i for i in result if isinstance(i, Request)]
                items = [self.pipeline_process(i, opts) for i in result if isinstance(i, ScrapedItem)]
                for item in items:
                    item.__dict__.pop('_adaptors_dict', None)

                display.nocolour = opts.nocolour
                if not opts.noitems:
                    print "# Scraped Items", "-"*60
                    display.pprint(items)

                if opts.nolinks:
                    print "# Links", "-"*68
                    display.pprint(links)
            else:
                log.msg('cannot find spider for url: %s' % response.url, level=log.ERROR)
