import sys
import os
from importlib import import_module

from scrapy.command import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.conf import arglist_to_dict
from scrapy.utils.iterators import iter_classes

class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "[options] <spider_file>"

    def short_desc(self):
        return "Run a self-contained spider (without creating a project)"

    def long_desc(self):
        return "Run the spider defined in the given file"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-a", dest="spargs", action="append", default=[], metavar="NAME=VALUE", \
            help="set spider argument (may be repeated)")
        parser.add_option("-o", "--output", metavar="FILE", \
            help="dump scraped items into FILE (use - for stdout)")
        parser.add_option("-t", "--output-format", metavar="FORMAT", default="jsonlines", \
            help="format to use for dumping items with -o (default: %default)")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError("Invalid -a value, use -a NAME=VALUE", print_help=False)
        if opts.output:
            if opts.output == '-':
                self.settings.overrides['FEED_URI'] = 'stdout:'
            else:
                self.settings.overrides['FEED_URI'] = opts.output
            valid_output_formats = self.settings['FEED_EXPORTERS'].keys() + self.settings['FEED_EXPORTERS_BASE'].keys()
            if opts.output_format not in valid_output_formats:
                raise UsageError('Invalid/unrecognized output format: %s, Expected %s' % (opts.output_format,valid_output_formats))
            self.settings.overrides['FEED_FORMAT'] = opts.output_format

    def run(self, args, opts):
        if len(args) != 1:
            raise UsageError()
        filename = args[0]
        if not os.path.exists(filename):
            raise UsageError("File not found: %s\n" % filename)
        spclasses = list(iter_classes(filename, "scrapy.spider", "Spider", is_file=True))
        if not spclasses:
            raise UsageError("No spider found in file: %s\n" % filename)
        spider = spclasses.pop()(**opts.spargs)

        crawler = self.crawler_process.create_crawler()
        crawler.crawl(spider)
        self.crawler_process.start()
