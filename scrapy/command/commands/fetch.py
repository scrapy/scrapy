import pprint

from scrapy import log
from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager
from scrapy.http import Request
from scrapy.spider import BaseSpider, spiders
from scrapy.utils.url import is_url

class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Fetch a URL using the Scrapy downloader"

    def long_desc(self):
        return "Fetch a URL using the Scrapy downloader and print its content " \
            "to stdout. You may want to use --nolog to disable logging"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--spider", dest="spider",
            help="use this spider")
        parser.add_option("--headers", dest="headers", action="store_true", \
            help="print response HTTP headers instead of body")

    def run(self, args, opts):
        if len(args) != 1 or not is_url(args[0]):
            return False
        responses = [] # to collect downloaded responses
        request = Request(args[0], callback=responses.append, dont_filter=True)

        if opts.spider:
            try:
                spider = spiders.create(opts.spider)
            except KeyError:
                log.msg("Could not find spider: %s" % opts.spider, log.ERROR)
        else:
            spider = scrapymanager._create_spider_for_request(request, \
                BaseSpider())

        scrapymanager.crawl_request(request, spider)
        scrapymanager.start()

        # display response
        if responses:
            if opts.headers:
                pprint.pprint(responses[0].headers)
            else:
                print responses[0].body

