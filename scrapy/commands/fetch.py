from w3lib.url import is_url

from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.exceptions import UsageError
from scrapy.utils.spider import create_spider_for_request
from urllib import quote

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
        parser.add_option("--post", dest="post", help="make a post request")
        parser.add_option("--data-binary", dest="data_binary", help="load file to post request")
        parser.add_option("--data-urlencode", dest="data_urlencode", help="urlencode data")
        parser.add_option("--content-type", dest="content_type", \
                  help="define Content-Type of HTTP request")

    def _print_headers(self, headers, prefix):
        for key, values in headers.items():
            for value in values:
                print '%s %s: %s' % (prefix, key, value)

    def _print_response(self, response, opts):
        if opts.headers:
            self._print_headers(response.request.headers, '>')
            print '>'
            self._print_headers(response.headers, '<')
        else:
            print response.body

    def run(self, args, opts):
        if len(args) != 1 or not is_url(args[0]):
            raise UsageError()
        cb = lambda x: self._print_response(x, opts)
        method_type = "GET"

        if opts.data_urlencode:
            #if string start @ is a file and load file content
            if opts.data_urlencode[0] == '@':
                opts.data_urlencode =  open(opts.data_urlencode[1:], 'r').read()
            opts.post = opts.data_urlencode[:opts.data_urlencode.index('=')+1] + \
                quote(opts.data_urlencode[opts.data_urlencode.index('=')+1:], safe='')

        if opts.data_binary:
            #if string start @ is a file and load file content
            if opts.data_binary[0] == '@':
                opts.post = open(opts.data_binary[1:], 'r').read()
            else:
                opts.post = opts.data_binary

        if opts.post:
            method_type = "POST"
        request = Request(args[0], method=method_type, 
                          body=opts.post, callback=cb, dont_filter=True)
        request.meta['handle_httpstatus_all'] = True
        if opts.content_type:
            request.headers['Content-Type'] = opts.content_type
        elif opts.post:
            request.headers['Content-Type'] = "application/x-www-form-urlencoded"

        crawler = self.crawler_process.create_crawler()
        spider = None
        if opts.spider:
            spider = crawler.spiders.create(opts.spider)
        else:
            spider = create_spider_for_request(crawler.spiders, request, \
                default_spider=BaseSpider('default'))
        crawler.crawl(spider, [request])
        self.crawler_process.start()
