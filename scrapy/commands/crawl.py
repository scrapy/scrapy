from scrapy.command import ScrapyCommand
from scrapy.utils.conf import arglist_to_dict
from scrapy.exceptions import UsageError

class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Run a spider"

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
                raise UsageError('Invalid/unrecognized output format: %s, Expected %s' % (opts.output_format, valid_output_formats))
            self.settings.overrides['FEED_FORMAT'] = opts.output_format

    def run(self, args, opts):
        if len(args) < 1:
            raise UsageError()
        elif len(args) > 1:
            raise UsageError("running 'scrapy crawl' with more than one spider is no longer supported")
        spname = args[0]

        crawler = self.crawler_process.create_crawler()
        spider = crawler.spiders.create(spname, **opts.spargs)
        crawler.crawl(spider)
        self.crawler_process.start()
