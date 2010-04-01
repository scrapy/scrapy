from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager
from scrapy.conf import settings
from scrapy.utils.url import is_url


class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] <domain|url> ..."

    def short_desc(self):
        return "Start crawling a domain or URL"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-n", "--nofollow", dest="nofollow", action="store_true", \
            help="don't follow links (for use with URLs only)")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        if opts.nofollow:
            settings.overrides['CRAWLSPIDER_FOLLOW_LINKS'] = False

    def run(self, args, opts):
        for arg in args:
            # schedule arg as url or domain
            if is_url(arg):
                scrapymanager.crawl_url(arg)
            else:
                scrapymanager.crawl_domain(arg)

        # crawl just scheduled arguments without keeping idle
        scrapymanager.start()
