from __future__ import print_function
from scrapy.command import ScrapyCommand

class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "[options]"

    def short_desc(self):
        return "Get settings values"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--get", dest="get", metavar="SETTING", \
            help="print raw setting value")
        parser.add_option("--getbool", dest="getbool", metavar="SETTING", \
            help="print setting value, intepreted as a boolean")
        parser.add_option("--getint", dest="getint", metavar="SETTING", \
            help="print setting value, intepreted as an integer")
        parser.add_option("--getfloat", dest="getfloat", metavar="SETTING", \
            help="print setting value, intepreted as an float")
        parser.add_option("--getlist", dest="getlist", metavar="SETTING", \
            help="print setting value, intepreted as an float")

    def run(self, args, opts):
        settings = self.crawler_process.settings
        if opts.get:
            print(settings.get(opts.get))
        elif opts.getbool:
            print(settings.getbool(opts.getbool))
        elif opts.getint:
            print(settings.getint(opts.getint))
        elif opts.getfloat:
            print(settings.getfloat(opts.getfloat))
        elif opts.getlist:
            print(settings.getlist(opts.getlist))
