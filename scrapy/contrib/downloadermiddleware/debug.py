from scrapy import log
from scrapy.core.exceptions import NotConfigured

class DebugMiddleware(object):

    def process_request(self, request, spider):
        log.msg("process_request %r" % request, domain=spider.domain_name, level=log.DEBUG)

    def process_exception(self, request, exception, spider):
        log.msg("process_exception %s in %r" % (exception, request), domain=spider.domain_name, level=log.DEBUG)

    def process_response(self, request, response, spider):
        log.msg("process_response %s from %r" % (response, request), domain=spider.domain_name, level=log.DEBUG)
        return response

# FIXME: backwards compatibility - will be removed before 0.7 release

import warnings

class CrawlDebug(object):

    def __init__(self):
        warnings.warn("scrapy.contrib.downloadermiddleware.debug.CrawlDebug has been replaced by scrapy.contrib.downloadermiddleware.debug.DebugDownloaderMiddleware")
        DebugMiddleware.__init__(self)
