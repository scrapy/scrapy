from scrapy.commands import ScrapyCommand
from scrapy.utils.conf import arglist_to_dict, feed_process_params_from_cli
from scrapy.exceptions import UsageError


class CommonCommands(ScrapyCommand):

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-a", dest="spargs", action="append", default=[],
                          metavar="NAME=VALUE",
                          help="set spider argument (may be repeated)")
        parser.add_option("-o", "--output", metavar="FILE", action="append",
                          help="dump scraped items into FILE"
                          + "(use - for stdout)")
        parser.add_option("-t", "--output-format", metavar="FORMAT",
                          help="format to use for dumping items with -o")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError(
                "Invalid -a value, use -a NAME=VALUE", print_help=False)
        if opts.output:
            feeds = feed_process_params_from_cli(
                self.settings, opts.output, opts.output_format)
            self.settings.set('FEEDS', feeds, priority='cmdline')
