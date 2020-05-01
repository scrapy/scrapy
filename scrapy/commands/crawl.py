from scrapy.commands import ScrapyCommand
from scrapy.utils.conf import arglist_to_dict, feed_process_params_from_cli
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Run a spider"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-a", dest="spargs", action="append", default=[], metavar="NAME=VALUE",
                          help="set spider argument (may be repeated)")
        parser.add_option("-o", "--output", metavar="FILE", action="append",
                          help="dump scraped items into FILE (use - for stdout)")
        parser.add_option("-t", "--output-format", metavar="FORMAT",
                          help="format to use for dumping items with -o")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError("Invalid -a value, use -a NAME=VALUE", print_help=False)
        if opts.output:
            feeds = feed_process_params_from_cli(self.settings, opts.output, opts.output_format)
            self.settings.set('FEEDS', feeds, priority='cmdline')

    def run(self, args, opts):
        if len(args) < 1:
            raise UsageError()
        elif len(args) > 1:
            raise UsageError("running 'scrapy crawl' with more than one spider is no longer supported")
        spname = args[0]

        crawl_defer = self.crawler_process.crawl(spname, **opts.spargs)

        if getattr(crawl_defer, 'result', None) is not None and issubclass(crawl_defer.result.type, Exception):
            self.exitcode = 1
        else:
            self.crawler_process.start()

            if self.crawler_process.bootstrap_failed or \
                    (hasattr(self.crawler_process, 'has_exception') and self.crawler_process.has_exception):
                self.exitcode = 1
