from scrapy import log
from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager
from scrapy.conf import settings
from scrapy.http import Request
from scrapy.spider import spiders
from scrapy.utils.url import is_url

from collections import defaultdict

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
        if opts.spider:
            spider = spiders.create(opts.spider)
        else:
            spider = None

        # aggregate urls and domains
        urls = []
        domains = []
        for arg in args:
            if is_url(arg):
                urls.append(arg)
            else:
                domains.append(arg)

        # schedule first domains
        for dom in domains:
            scrapymanager.crawl_domain(dom)

        # if forced spider schedule urls directly
        if spider:
            for url in urls:
                scrapymanager.crawl_url(url, spider)
        else:
            # group urls by spider
            spider_urls = defaultdict(list)
            find_by_url = lambda url: spiders.find_by_request(Request(url))
            for url in urls:
                spider_names = find_by_url(url)
                if not spider_names:
                    log.msg('Could not find spider for url: %s' % url,
                            log.ERROR)
                elif len(spider_names) > 1:
                    log.msg('More than one spider found for url: %s' % url,
                            log.ERROR)
                else:
                    spider_urls[spider_names[0]].append(url)

            # schedule grouped urls with same spider
            for name, urls in spider_urls.iteritems():
                # instance spider for each url-list
                spider = spiders.create(name)
                for url in urls:
                    scrapymanager.crawl_url(url, spider)

        # crawl just scheduled arguments without keeping idle
        scrapymanager.start()
