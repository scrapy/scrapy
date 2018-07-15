"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""
from threading import Thread

from scrapy.commands import ScrapyCommand
from scrapy.shell import Shell
from scrapy.http import Request
from scrapy.utils.spider import spidercls_for_request, DefaultSpider
from scrapy.utils.url import guess_scheme


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {
        'KEEP_ALIVE': True,
        'LOGSTATS_INTERVAL': 0,
        'DUPEFILTER_CLASS': 'scrapy.dupefilters.BaseDupeFilter',
    }

    def syntax(self):
        return "[url|file]"

    def short_desc(self):
        return "Interactive scraping console"

    def long_desc(self):
        return "Interactive console for scraping the given url"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-c", dest="code",
            help="evaluate the code in the shell, print the result and exit")
        parser.add_option("--spider", dest="spider",
            help="use this spider")
        parser.add_option("--no-redirect", dest="no_redirect", action="store_true", \
            default=False, help="do not handle HTTP 3xx status codes and print response as-is")

    def update_vars(self, vars):
        """You can use this function to update the Scrapy objects that will be
        available in the shell
        """
        pass

    def run(self, args, opts):
        url = args[0] if args else None
        if url:
            # first argument may be a local file
            url = guess_scheme(url)

        spider_loader = self.crawler_process.spider_loader

        spidercls = DefaultSpider
        if opts.spider:
            spidercls = spider_loader.load(opts.spider)
        elif url:
            spidercls = spidercls_for_request(spider_loader, Request(url),
                                              spidercls, log_multiple=True)

        # The crawler is created this way since the Shell manually handles the
        # crawling engine, so the set up in the crawl method won't work
        crawler = self.crawler_process._create_crawler(spidercls)
        # The Shell class needs a persistent engine in the crawler
        crawler.engine = crawler._create_engine()
        crawler.engine.start()

        self._start_crawler_thread()

        shell = Shell(crawler, update_vars=self.update_vars, code=opts.code)
        shell.start(url=url, redirect=not opts.no_redirect)

    def _start_crawler_thread(self):
        t = Thread(target=self.crawler_process.start,
                   kwargs={'stop_after_crawl': False})
        t.daemon = True
        t.start()
