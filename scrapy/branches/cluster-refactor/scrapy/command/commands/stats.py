import pprint
from scrapy.command import ScrapyCommand
from scrapy.conf import settings

class Command(ScrapyCommand):
    def syntax(self):
        return "<domain> [domain ...]"

    def short_desc(self):
        return "Show all stats history stored for the given domain(s)"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-p", "--path", dest="path", help="restrict stats to PATH", metavar="PATH")

    def run(self, args, opts):
        if not args:
            print "A domain is required"
            return
        if not settings['SCRAPING_DB']:
            print "SCRAPING_DB setting is required for this command"
            return

        from scrapy.store.db import DomainDataHistory
        ddh = DomainDataHistory(settings['SCRAPING_DB'], 'domain_data_history')

        for domain in args:
            print "# %s" % domain
            pprint.pprint(list(ddh.getall(domain, opts.path)))

