import sys
import os

from scrapy import log
from scrapy.utils.spider import iter_spider_classes
from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager

def _import_file(filepath):
    abspath = os.path.abspath(filepath)
    dirname, file = os.path.split(abspath)
    fname, fext = os.path.splitext(file)
    if fext != '.py':
        raise ValueError("Not a Python source file: %s" % abspath)
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
        return "Run the spider defined in the given file"

    def run(self, args, opts):
        if len(args) != 1:
            return False
        filename = args[0]
        if not os.path.exists(filename):
            log.msg("File not found: %s\n" % filename, log.ERROR)
            return
        try:
            module = _import_file(filename)
        except (ImportError, ValueError), e:
            log.msg("Unable to load %r: %s\n" % (filename, e), log.ERROR)
            return
        spclasses = list(iter_spider_classes(module))
        if not spclasses:
            log.msg("No spider found in file: %s\n" % filename, log.ERROR)
            return
        spider = spclasses.pop()()
        # schedule spider and start engine
        scrapymanager.queue.append_spider(spider)
        scrapymanager.start()
