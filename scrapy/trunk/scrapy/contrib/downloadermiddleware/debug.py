from scrapy import log
from scrapy.conf import settings

class CrawlDebug(object):
    def __init__(self):
        self.enabled = settings.getbool('CRAWL_DEBUG')
    
    def process_request(self, request, spider):
        if self.enabled:
            log.msg("Crawling %s" % repr(request), domain=spider.domain_name, level=log.DEBUG)

    def process_exception(self, request, exception, spider):
        if self.enabled:
            log.msg("Crawl exception %s in %s" % (exception, repr(request)), domain=spider.domain_name, level=log.DEBUG)

    def process_response(self, request, response, spider):
        if self.enabled:
            log.msg("Fetched %s from %s" % (response.info(), repr(request)), domain=spider.domain_name, level=log.DEBUG)
        return response

