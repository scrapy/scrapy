"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

from threading import Thread

from scrapy.command import ScrapyCommand
from scrapy.shell import Shell
from scrapy.http import Request
from scrapy import settings

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
        parser.add_option("--post", dest="post", help="make a post request")

    def update_vars(self, vars):
        """You can use this function to update the Scrapy objects that will be
        available in the shell
        """
        pass

    def run(self, args, opts):
        crawler = self.crawler_process.create_crawler()

        url = args[0] if args else None
        spider = crawler.spiders.create(opts.spider) if opts.spider else None

        self.crawler_process.start_crawling()
        self._start_crawler_thread()

        shell = Shell(crawler, update_vars=self.update_vars, code=opts.code)
        
        if opts.post:
            header = settings.default_settings.DEFAULT_REQUEST_HEADERS
            header['Content-Type'] = "application/x-www-form-urlencoded"            
            
            request = Request(url, method="POST", headers=header,
                              body=opts.post, dont_filter=True)
            shell.start(request=request, spider=spider)
        else:
            shell.start(url=url, spider=spider)

    def _start_crawler_thread(self):
        t = Thread(target=self.crawler_process.start_reactor)
        t.daemon = True
        t.start()
