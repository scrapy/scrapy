from scrapy import log
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

class CrawlDebug(object):

    def __init__(self):
        raise NotConfigured
    
    def process_request(self, request, spider):
        log.msg("Crawling %s" % repr(request), domain=spider.domain_name, level=log.DEBUG)

    def process_exception(self, request, exception, spider):
        log.msg("Crawl exception %s in %s" % (exception, repr(request)), domain=spider.domain_name, level=log.DEBUG)

    def process_response(self, request, response, spider):
        log.msg("Fetched %s from %s" % (response, repr(request)), domain=spider.domain_name, level=log.DEBUG)
        return response

