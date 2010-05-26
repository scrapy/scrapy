from scrapy import log
from scrapy.command import ScrapyCommand
from scrapy.core.queue import ExecutionQueue
from scrapy.core.manager import scrapymanager
from scrapy.conf import settings
from scrapy.http import Request
from scrapy.spider import spiders
from scrapy.utils.url import is_url

from collections import defaultdict

class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] <spider|url> ..."

    def short_desc(self):
        return "Start crawling from a spider or URL"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--spider", dest="spider", default=None, \
            help="always use this spider when arguments are urls")
        parser.add_option("-n", "--nofollow", dest="nofollow", action="store_true", \
            help="don't follow links (for use with URLs only)")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        if opts.nofollow:
            settings.overrides['CRAWLSPIDER_FOLLOW_LINKS'] = False

    def run(self, args, opts):
        q = ExecutionQueue()
        urls, names = self._split_urls_and_names(args)
        for name in names:
            q.append_spider_name(name)

        if opts.spider:
            try:
                spider = spiders.create(opts.spider)
                for url in urls:
                    q.append_url(url, spider)
            except KeyError:
                log.msg('Unable to find spider: %s' % opts.spider, log.ERROR)
        else:
            for name, urls in self._group_urls_by_spider(urls):
                spider = spiders.create(name)
                for url in urls:
                    q.append_url(url, spider)

        scrapymanager.queue = q
        scrapymanager.start()

    def _group_urls_by_spider(self, urls):
        spider_urls = defaultdict(list)
        for url in urls:
            spider_names = spiders.find_by_request(Request(url))
            if not spider_names:
                log.msg('Could not find spider for url: %s' % url,
                        log.ERROR)
            elif len(spider_names) > 1:
                log.msg('More than one spider found for url: %s' % url,
                        log.ERROR)
            else:
                spider_urls[spider_names[0]].append(url)
        return spider_urls.items()

    def _split_urls_and_names(self, args):
        urls = []
        names = []
        for arg in args:
            if is_url(arg):
                urls.append(arg)
            else:
                names.append(arg)
        return urls, names
