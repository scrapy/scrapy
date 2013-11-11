from optparse import OptionGroup
from mimetypes import guess_type

from scrapy.command import ScrapyCommand
from scrapy.commands import fetch
from scrapy.utils.response import open_in_browser

class Command(fetch.Command):

    def short_desc(self):
        return "Open URL in browser, as seen by Scrapy"

    def long_desc(self):
        return "Fetch a URL using the Scrapy downloader and show its " \
            "contents in a browser"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
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

    def _print_response(self, response, opts):
        open_in_browser(response)
