from scrapy.command import ScrapyCommand
from scrapy.conf import settings as settings_

class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "[options]"

    def short_desc(self):
        return "Query Scrapy settings"

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
        parser.add_option("--init", dest="init", action="store_true", \
            help="print initial setting value (before loading extensions and spiders)")

    def process_options(self, args, opts):
        super(Command, self).process_options(args, opts)
        if opts.init:
            self._print_setting(opts)

    def run(self, args, opts):
        if not opts.init:
            self._print_setting(opts)

    def _print_setting(self, opts):
        if opts.get:
            print settings_.get(opts.get)
        elif opts.getbool:
            print settings_.getbool(opts.getbool)
        elif opts.getint:
            print settings_.getint(opts.getint)
        elif opts.getfloat:
            print settings_.getfloat(opts.getfloat)
        elif opts.getlist:
            print settings_.getlist(opts.getlist)
