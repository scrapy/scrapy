from scrapy.command import ScrapyCommand
from scrapy.utils.conf import arglist_to_dict
from scrapy.exceptions import UsageError

class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Start crawling from a spider or URL"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-a", dest="spargs", action="append", default=[], metavar="NAME=VALUE", \
            help="set spider argument (may be repeated)")
        parser.add_option("-o", "--output", metavar="FILE", \
            help="store scraped items into FILE (using feed exports)")
        parser.add_option("-t", "--output-format", metavar="FORMAT", default="jsonlines", \
            help="format to use in feed exports (default: %default)")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError("Invalid -a value, use -a NAME=VALUE", print_help=False)
        if opts.output:
            self.settings.overrides['FEED_URI'] = opts.output
            self.settings.overrides['FEED_FORMAT'] = opts.output_format

    def run(self, args, opts):
        if len(args) < 1:
            raise UsageError()
        elif len(args) > 1:
            raise UsageError("running 'scrapy crawl' with more than one spider is no longer supported")
        for spname in args:
            spider = self.crawler.spiders.create(spname, **opts.spargs)
            self.crawler.crawl(spider)
        self.crawler.start()
