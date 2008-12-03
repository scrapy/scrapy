from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager
from scrapy.replay import Replay
from scrapy.conf import settings
from scrapy.utils.url import is_url
from scrapy.spider import spiders
from scrapy.http import Request
from scrapy import log


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
        parser.add_option("-n", "--nofollow", dest="nofollow", action="store_true", help="don't follow links (for use with URLs only)")
        parser.add_option("-c", "--callback", dest="callback", action="store", help="use the provided callback for starting to crawl the given url")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        if opts.nopipeline:
            settings.overrides['ITEM_PIPELINES'] = []

        if opts.nocache:
            settings.overrides['CACHE2_DIR'] = None

        if opts.restrict:
            settings.overrides['RESTRICT_TO_URLS'] = args

        if opts.nofollow:
            settings.overrides['CRAWLSPIDER_FOLLOW_LINKS'] = False

        if opts.record or opts.recorddir:
            # self.replay is used for preventing Replay signals handler from
            # disconnecting since pydispatcher uses weak references 
            self.replay = Replay(opts.record or opts.recorddir, mode='record', usedir=bool(opts.recorddir))
            self.replay.record(args=args, opts=opts.__dict__)

    def run(self, args, opts):
        if opts.callback:
            requests = []
            for a in args:
                if is_url(a):
                    spider = spiders.fromurl(a)
                    urls = [a]
                else:
                    spider = spiders.fromdomain(a)
                    urls = spider.start_urls if hasattr(spider.start_urls, '__iter__') else [spider.start_urls]

                if spider:
                    if hasattr(spider, opts.callback):
                        requests.extend(Request(url=url, callback=getattr(spider, opts.callback)) for url in urls)
                    else:
                        log.msg('Callback %s doesnt exist in spider %s' % (opts.callback, spider.domain_name), log.ERROR)
                else:
                    log.msg('Could not found spider for %s' % a, log.ERROR)

            if requests:
                args = requests
            else:
                log.msg('Couldnt create any requests from the provided arguments', log.ERROR)
                return

        scrapymanager.runonce(*args, **opts.__dict__)
