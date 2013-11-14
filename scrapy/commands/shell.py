"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

from urllib import quote
from threading import Thread
from optparse import OptionGroup
from mimetypes import guess_type

from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.shell import Shell


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
        parser.add_option("-d", "--data", dest="data", \
                          help="HTTP POST data. See more options below")
        
        group = OptionGroup(parser, "HTTP POST Options")
        group.add_option("--data-binary", metavar="FILE", dest="data_binary", \
                         help="HTTP POST binary data found in FILE")
        group.add_option("--data-urlencode", dest="data_urlencode", \
                         help="HTTP POST data url encoded")
        group.add_option("--data-content-type", dest="content_type", \
                  help="define Content-Type header of the HTTP POST request")
        parser.add_option_group(group)

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

        if opts.data or opts.data_binary or opts.data_urlencode:
            content_type = None
            if opts.data:
                data = opts.data
            elif opts.data_urlencode:
                data = quote(opts.data_urlencode, safe='=')
            elif opts.data_binary:
                try:
                    data = open(opts.data_binary, 'rb').read()
                    (content_type, enconding) = guess_type(opts.data_binary)
                except IOError:
                    raise UsageError("This option expects a filename")

            request = Request(url, method="POST", body=data, dont_filter=True)
            
            request.headers['Content-Type'] = "application/x-www-form-urlencoded"
            request.meta['handle_httpstatus_all'] = True

            if opts.content_type:
                request.headers['Content-Type'] = opts.content_type
            elif content_type:
                request.headers['Content-Type'] = content_type
            shell.start(request=request, spider=spider)

        elif opts.content_type:
            raise UsageError("This option only works when sending POST data")
        else:
            shell.start(url=url, spider=spider)

    def _start_crawler_thread(self):
        t = Thread(target=self.crawler_process.start_reactor)
        t.daemon = True
        t.start()
