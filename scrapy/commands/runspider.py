import sys
import os
from importlib import import_module

from scrapy.utils.spider import iter_spider_classes
from scrapy.exceptions import UsageError
from scrapy.commands import BaseRunSpiderCommand


def _import_file(filepath):
    abspath = os.path.abspath(filepath)
    dirname, file = os.path.split(abspath)
    fname, fext = os.path.splitext(file)
    if fext not in ('.py', '.pyw'):
        raise ValueError(f"Not a Python source file: {abspath}")
    if dirname:
        sys.path = [dirname] + sys.path
    try:
        module = import_module(fname)
    finally:
        if dirname:
            sys.path.pop(0)
    return module


class Command(BaseRunSpiderCommand):

    requires_project = False
    default_settings = {'SPIDER_LOADER_WARN_ONLY': True}

    def syntax(self):
        return "[options] <spider_file>"

    def short_desc(self):
        return "Run a self-contained spider (without creating a project)"

    def long_desc(self):
        return "Run the spider defined in the given file"

    def run(self, args, opts):
        if len(args) != 1:
            raise UsageError()
        filename = args[0]
        if not os.path.exists(filename):
            raise UsageError(f"File not found: {filename}\n")
        try:
            module = _import_file(filename)
        except (ImportError, ValueError) as e:
            raise UsageError(f"Unable to load {filename!r}: {e}\n")
        spclasses = list(iter_spider_classes(module))
        if not spclasses:
            raise UsageError(f"No spider found in file: {filename}\n")
        spidercls = spclasses.pop()

        self.crawler_process.crawl(spidercls, **opts.spargs)
        self.crawler_process.start()

        if self.crawler_process.bootstrap_failed:
            self.exitcode = 1
