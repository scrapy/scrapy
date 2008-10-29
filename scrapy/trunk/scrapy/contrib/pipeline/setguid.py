"""
This pipeline sets the guid for each scraped item.
It should be the previous to the validation pipeline (which is the last one).
"""

from pydispatch import dispatcher
from scrapy.core import signals

class SetGUIDPipeline(object):
    def __init__(self):
        self.spider = None
        dispatcher.connect(self.domain_opened, signal=signals.domain_opened)

    def domain_opened(self, domain, spider):
        self.spider = spider

    def process_item(self, domain, response, item):
        self.spider.set_guid(item)
        return item

