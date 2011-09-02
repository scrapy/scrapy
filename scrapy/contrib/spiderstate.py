from __future__ import with_statement

import os, cPickle as pickle

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.xlib.pydispatch import dispatcher

class SpiderState(object):
    """Stores and loads spider state"""

    def __init__(self, jobdir):
        self.statefn = os.path.join(jobdir, 'spider.state')
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)
        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)

    @classmethod
    def from_crawler(cls, crawler):
        jobdir = crawler.settings.get('JOBDIR')
        if not jobdir:
            raise NotConfigured
        return cls(jobdir)

    def spider_closed(self, spider):
        with open(self.statefn, 'wb') as f:
            pickle.dump(spider.state, f, protocol=2)

    def spider_opened(self, spider):
        if os.path.exists(self.statefn):
            with open(self.statefn) as f:
                spider.state = pickle.load(f)
        else:
            spider.state = {}
