"""
Pipeline to print Items
"""
from scrapy import log
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

class ShowItemPipeline(object):
    def __init__(self):
        if not settings['DEBUG_SHOWITEM']:
            raise NotConfigured

    def process_item(self, domain, response, item):
        log.msg("Scraped: \n%s" % repr(item), log.DEBUG, domain=domain)
        return item
