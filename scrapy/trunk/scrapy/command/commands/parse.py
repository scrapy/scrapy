from scrapy.command.commands.parse_method import Command as ScrapyCommand
from scrapy.fetcher import fetch
from scrapy.spider import spiders
from scrapy import log

class Command(ScrapyCommand):
    def syntax(self):
        return "[options] <url>"

    def short_desc(self):
        return "Parse the URL and print its results"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--identify", dest="identify", action="store_true", help="try to use identify instead of parse")

    def run(self, args, opts):
        if not args:
            print "A URL is required"
            return

        items = set()
        links = set()
        responses = fetch(args)
        for response in responses:
            spider = spiders.fromurl(response.url)
            if spider:
                if opts.identify and hasattr(spider, 'identify_products'):
                    ret_items, ret_links = ScrapyCommand.run_method(self, response, 'identify_products', args, opts)
                else:
                    if hasattr(spider, 'rules'):
                        for rule in spider.rules:
                            if rule.link_extractor.match(response.url):
                                ret_items, ret_links = ScrapyCommand.run_method(self, response, rule.callback, args, opts)
                                break
                    else:
                        ret_items, ret_links = ScrapyCommand.run_method(self, response, 'parse', args, opts)
                    items = items.union(ret_items)
                    links = links.union(ret_links)
            else:
                log.msg('Couldnt find method %s in spider %s' % (method, spider.__name__))
                continue

        self.print_results(items, links, opts)

