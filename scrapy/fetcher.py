import urlparse

from scrapy.spider import spiders
from scrapy.http import Request
from scrapy.core.manager import scrapymanager
from scrapy.spider import BaseSpider

def fetch(urls, perdomain=False):
    """Download a set of urls. This is starts a reactor and is suitable
    for calling from a main method - not for calling from within the 
    framework.

    It will return a list of Response objects for all pages successfully
    downloaded.
    """
    bigbucket = {} # big bucket to store response objects (per domain)

    def _add(response, domain):
        if not domain in bigbucket:
            bigbucket[domain] = []
        bigbucket[domain] += [response]

    # url clasification by domain
    requestdata = set()
    for url in urls:
        domain = get_or_create_spider(url).domain_name
        request = Request(url=url, callback=lambda r: _add(r, domain), dont_filter=True)
        requestdata.add(request)

    scrapymanager.runonce(*requestdata)

    # returns bigbucket as dict or flatted
    if perdomain:
        return bigbucket

    flatbucket = []
    for domain, responses in bigbucket.iteritems():
        flatbucket.extend(responses)
    return flatbucket


def get_or_create_spider(url):
    # XXX: hack to allow downloading pages from unknown domains
    spider = spiders.fromurl(url)
    if not spider:
        domain = str(urlparse.urlparse(url).hostname or spiders.default_domain)
        spider = BaseSpider()
        spider.domain_name = domain
        spiders.add_spider(spider)
    return spider

