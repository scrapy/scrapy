import scrapy
from scrapy.command import ScrapyCommand

class Command(ScrapyCommand):

    def short_desc(self):
        return "Print Scrapy version"

    def run(self, args, opts):
        print "Scrapy %s" % scrapy.__version__
