import sys
import platform

import twisted

import scrapy
from scrapy.command import ScrapyCommand

class Command(ScrapyCommand):

    def syntax(self):
        return "[-v]"

    def short_desc(self):
        return "Print Scrapy version"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--verbose", "-v", dest="verbose", action="store_true",
            help="also display twisted/python/platform info (useful for bug reports)")

    def run(self, args, opts):
        if opts.verbose:
            print "Scrapy  : %s" % scrapy.__version__
            print "Twisted : %s" % twisted.version.short()
            print "Python  : %s" % sys.version.replace("\n", "- ")
            print "Platform: %s" % platform.platform()
        else:
            print "Scrapy %s" % scrapy.__version__
