import sys, pprint

from scrapy.command import ScrapyCommand
from scrapy.fetcher import fetch

class Command(ScrapyCommand):
    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Download a URL using the Scrapy downloader"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-s", "--source", dest="source", action="store_true", help="output HTTP body only")
        parser.add_option("--headers", dest="headers", action="store_true", help="output HTTP headers only")

    def run(self, args, opts):
        if not args:
            print "A URL is required"
            return

        responses = fetch(args)
        if responses:
            if opts.headers:
                pprint.pprint(responses[0].headers)
            else:
                sys.stdout.write(str(responses[0].body))
