"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

from threading import Thread

from scrapy.command import ScrapyCommand
from scrapy.shell import Shell
from scrapy import log

class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'KEEP_ALIVE': True, 'LOGSTATS_INTERVAL': 0}

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

    def update_vars(self, vars):
        """You can use this function to update the Scrapy objects that will be
        available in the shell
        """
        pass

    def run(self, args, opts):
        url = args[0] if args else None
        spider = None
        if opts.spider:
            spider = self.crawler.spiders.create(opts.spider)
        shell = Shell(self.crawler, update_vars=self.update_vars, code=opts.code)
        self._start_crawler_thread()
        shell.start(url=url, spider=spider)

    def _start_crawler_thread(self):
        t = Thread(target=self.crawler.start)
        t.daemon = True
        t.start()
