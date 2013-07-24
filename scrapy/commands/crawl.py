from scrapy.command import ScrapyCommand
from scrapy.utils.conf import arglist_to_dict
from scrapy.exceptions import UsageError
from optparse import OptionGroup

class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Start crawling from a spider or URL"

    @classmethod
    def _pop_spider_name(cls, argv):
        i = 0
        for arg in argv:
            if not arg.startswith('-'):
                del argv[i]
                return arg
            i += 1

    def add_options(self, parser, argv=[]):
        spidername = self._pop_spider_name(argv)
        super(Command, self).add_options(parser, argv)

        parser.add_option("-a", dest="spargs", action="append", default=[], metavar="NAME=VALUE", \
            help="set spider argument (may be repeated)")
        parser.add_option("-o", "--output", metavar="FILE", \
            help="dump scraped items into FILE (use - for stdout)")
        parser.add_option("-t", "--output-format", metavar="FORMAT", default="jsonlines", \
            help="format to use for dumping items with -o (default: %default)")

        # per spider options (if any)
        self.add_spider_options(parser, spidername)

    def add_spider_options(self, parser, spidername):
        option_list = self.crawler.spiders.get_option_list(spidername)
        if option_list:
            group = OptionGroup(parser, "Spider-specific Options")
            for option in option_list:
                group.add_option(option)
            parser.add_option_group(group)

    def process_options(self, args, opts):
        super(Command, self).process_options(args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError("Invalid -a value, use -a NAME=VALUE", print_help=False)

        # add command-line options to spider runtime arguments (if any)
        spider_options = getattr(opts, 'spideropts', None)
        if spider_options:
            opts.spargs['cmdopts'] = spider_options

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
        if len(args) < 1:
            raise UsageError()
        elif len(args) > 1:
            raise UsageError("running 'scrapy crawl' with more than one spider is no longer supported")
        spname = args[0]
        spider = self.crawler.spiders.create(spname, **opts.spargs)
        self.crawler.crawl(spider)
        self.crawler.start()
