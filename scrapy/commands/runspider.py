import sys
import os
from importlib import import_module

from scrapy.utils.spider import iter_spider_classes
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.conf import arglist_to_dict, feed_process_params_from_cli


def _import_file(filepath):
    abspath = os.path.abspath(filepath)
    dirname, file = os.path.split(abspath)
    fname, fext = os.path.splitext(file)
    if fext != '.py':
        raise ValueError("Not a Python source file: %s" % abspath)
    if dirname:
        sys.path = [dirname] + sys.path
    try:
        module = import_module(fname)
    finally:
        if dirname:
            sys.path.pop(0)
    return module


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'SPIDER_LOADER_WARN_ONLY': True}

    def syntax(self):
        return "[options] <spider_file>"

    def short_desc(self):
        return "Run a self-contained spider (without creating a project)"

    def long_desc(self):
        return "Run the spider defined in the given file"

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
        if len(args) != 1:
            raise UsageError()
        filename = args[0]
        if not os.path.exists(filename):
            raise UsageError("File not found: %s\n" % filename)
        try:
            module = _import_file(filename)
        except (ImportError, ValueError) as e:
            raise UsageError("Unable to load %r: %s\n" % (filename, e))
        spclasses = list(iter_spider_classes(module))
        if not spclasses:
            raise UsageError("No spider found in file: %s\n" % filename)
        spidercls = spclasses.pop()

        self.crawler_process.crawl(spidercls, **opts.spargs)
        self.crawler_process.start()

        if self.crawler_process.bootstrap_failed:
            self.exitcode = 1
