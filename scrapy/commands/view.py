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
        parser.add_option("--post", dest="post", help="make a post request")
        parser.add_option("--content-type", dest="content_type", \
                  help="define Content-Type of HTTP request")

    def _print_response(self, response, opts):
        open_in_browser(response)
