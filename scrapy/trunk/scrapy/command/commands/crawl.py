from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager
from scrapy.replay import Replay
from scrapy.report import Report
from scrapy.conf import settings


class Command(ScrapyCommand):
    def syntax(self):
        return "[options] [domain|url] ..."

    def short_desc(self):
        return "Run the web scraping engine from the command line"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--nocache", dest="nocache", action="store_true", help="disable HTTP cache")
        parser.add_option("--nopipeline", dest="nopipeline", action="store_true", help="disable scraped item pipeline")
        parser.add_option("--restrict", dest="restrict", action="store_true", help="restrict crawling only to the given urls")
        parser.add_option("--record", dest="record", help="use FILE for recording session (see replay command)", metavar="FILE")
        parser.add_option("--record-dir", dest="recorddir", help="use DIR for recording (instead of file)", metavar="DIR")
        parser.add_option("--report", dest="doreport", action='store_true', help="generate a report of the scraped products in a text file")
        parser.add_option("--report-dropped", dest="doreport_dropped", action="store_true", help="generate a report of the dropped products in a text file")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        if opts.nopipeline:
            settings.overrides['ITEM_PIPELINES'] = []

        if opts.nocache:
            settings.overrides['CACHE2_DIR'] = None

        if opts.restrict:
            settings.overrides['RESTRICT_TO_URLS'] = args

        if opts.record or opts.recorddir:
            # self.replay is used for preventing Replay signals handler from
            # disconnecting since pydispatcher uses weak references 
            self.replay = Replay(opts.record or opts.recorddir, mode='record', usedir=bool(opts.recorddir))
            self.replay.record(args=args, opts=opts.__dict__)
        if opts.doreport or opts.doreport_dropped:
            self.report = Report(passed=opts.doreport, dropped=opts.doreport_dropped)

    def run(self, args, opts):
        scrapymanager.runonce(*args, **opts.__dict__)
