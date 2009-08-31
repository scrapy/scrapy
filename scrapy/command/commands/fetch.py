import pprint

from scrapy.command import ScrapyCommand
from scrapy.fetcher import fetch

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
        parser.add_option("--headers", dest="headers", action="store_true", \
            help="print HTTP headers instead of body")

    def run(self, args, opts):
        if not args:
            print "A URL is required"
            return

        responses = fetch(args)
        if responses:
            if opts.headers:
                pprint.pprint(responses[0].headers)
            else:
                print responses[0].body
