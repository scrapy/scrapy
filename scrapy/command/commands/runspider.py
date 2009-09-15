import sys
import os

from scrapy.xlib.pydispatch import dispatcher
from scrapy.contrib.exporter import XmlItemExporter
from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager
from scrapy.core import signals

def _import_file(filepath):
    abspath = os.path.abspath(filepath)
    dirname, file = os.path.split(abspath)
    fname, fext = os.path.splitext(file)
    if fext != '.py':
        raise ValueError("Only Python files supported: %s" % abspath)
    if dirname:
        sys.path = [dirname] + sys.path
    try:
        module = __import__(fname, {}, {}, [''])
    finally:
        if dirname:
            sys.path.pop(0)
    return module


class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "[options] <spider_file>"

    def short_desc(self):
        return "Run a spider"

    def long_desc(self):
        return "Run the spider defined in the given file. The file must be a " \
            "Python module which defines a SPIDER variable with a instance of " \
            "the spider to run."

    def add_options(self, parser):
        super(Command, self).add_options(parser)
        parser.add_option("--output", dest="output", metavar="FILE",
            help="store scraped items to FILE in XML format")

    def run(self, args, opts):
        if len(args) != 1:
            return False
        if opts.output:
            file = open(opts.output, 'w+b')
            exporter = XmlItemExporter(file)
            dispatcher.connect(exporter.export_item, signal=signals.item_passed)
            exporter.start_exporting()
        module = _import_file(args[0])
        scrapymanager.runonce(module.SPIDER)
        if opts.output:
            exporter.finish_exporting()
