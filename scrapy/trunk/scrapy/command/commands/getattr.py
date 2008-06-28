from scrapy.command import ScrapyCommand
from scrapy.fetcher import fetch
from scrapy.spider import spiders
from scrapy.item import ScrapedItem

def get_item_attr(pagedata, attr="guid"):
    spider = spiders.fromurl(pagedata.url)
    items = spider.parse(pagedata)
    attrs = [getattr(i, attr) for i in items if isinstance(i, ScrapedItem)]
    return attrs

def get_attr(url, attr="guid"):
    pagedatas = fetch([url])
    if pagedatas:
        return get_item_attr(pagedatas[0], attr)

class Command(ScrapyCommand):
    def syntax(self):
        return "<url> <attribute>"

    def short_desc(self):
        return "Print an attribute from the item scraped in the given URL"

    def run(self, args, opts):
        print get_attr(args[0], args[1])
