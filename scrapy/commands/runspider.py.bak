import sys
import os
from importlib import import_module

from scrapy.utils.spider import iter_spider_classes
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.conf import arglist_to_dict
from scrapy.utils.python import without_none_values


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
        parser.add_option("-o", "--output", metavar="FILE",
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
            if opts.output == '-':
                self.settings.set('FEED_URI', 'stdout:', priority='cmdline')
            else:
                self.settings.set('FEED_URI', opts.output, priority='cmdline')
            feed_exporters = without_none_values(self.settings.getwithbase('FEED_EXPORTERS'))
            valid_output_formats = feed_exporters.keys()
            if not opts.output_format:
                opts.output_format = os.path.splitext(opts.output)[1].replace(".", "")
            if opts.output_format not in valid_output_formats:
                raise UsageError("Unrecognized output format '%s', set one"
                                 " using the '-t' switch or as a file extension"
                                 " from the supported list %s" % (opts.output_format,
                                                                  tuple(valid_output_formats)))
            self.settings.set('FEED_FORMAT', opts.output_format, priority='cmdline')

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
