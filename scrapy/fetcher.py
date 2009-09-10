from urlparse import urlparse

from scrapy.spider import spiders
from scrapy.http import Request
from scrapy.core.manager import scrapymanager
from scrapy.spider import BaseSpider

def fetch(urls):
    """Download the given urls and return a list of the successfully downloaded
    responses.

    Suitable for for calling from a script, shouldn't be called from spiders.
    """
    map(get_or_create_spider, urls)
    responses = []
    requests = [Request(url, callback=responses.append, dont_filter=True) \
        for url in urls]
    scrapymanager.runonce(*requests)
    return responses

def get_or_create_spider(url):
    # XXX: hack to allow downloading pages from unknown domains
    spider = spiders.fromurl(url)
    if not spider:
        domain = urlparse(url).hostname
        spider = BaseSpider()
        spider.domain_name = domain
        spiders.add_spider(spider)
    return spider

