from __future__ import print_function
from w3lib.url import is_url
from urllib import quote
from optparse import OptionGroup
from mimetypes import guess_type

from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.spider import Spider
from scrapy.exceptions import UsageError
from scrapy.utils.spider import create_spider_for_request

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

    def _print_headers(self, headers, prefix):
        for key, values in headers.items():
            for value in values:
                print('%s %s: %s' % (prefix, key, value))

    def _print_response(self, response, opts):
        if opts.headers:
            self._print_headers(response.request.headers, '>')
            print('>')
            self._print_headers(response.headers, '<')
        else:
            print(response.body)

    def run(self, args, opts):
        if len(args) != 1 or not is_url(args[0]):
            raise UsageError()
        cb = lambda x: self._print_response(x, opts)
        
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

            request = Request(args[0], method="POST", 
                              body=data, callback=cb, dont_filter=True)
            
            request.headers['Content-Type'] = "application/x-www-form-urlencoded"

            if opts.content_type:
                request.headers['Content-Type'] = opts.content_type
            elif content_type:
                request.headers['Content-Type'] = content_type
        elif opts.content_type:
            raise UsageError("This option only works when sending POST data")
        else:
            request = Request(args[0], callback=cb, dont_filter=True)
        
        request.meta['handle_httpstatus_all'] = True
        
        crawler = self.crawler_process.create_crawler()
        spider = None
        if opts.spider:
            spider = crawler.spiders.create(opts.spider)
        else:
            spider = create_spider_for_request(crawler.spiders, request, \
                default_spider=Spider('default'))
        crawler.crawl(spider, [request])
        self.crawler_process.start()
