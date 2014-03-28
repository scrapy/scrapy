
####
#   The changes to the following block is targeted at making scrapy available
#   in both Python 2.7 and Python 3.x . The original code is commented out.

#import os, cPickle as pickle

try:
    import os, cPickle as pickle
except ImportError: 
    import os, pickle

####




from scrapy import signals

class SpiderState(object):
    """Store and load spider state during a scraping job"""

    def __init__(self, jobdir=None):
        self.jobdir = jobdir

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls(crawler.settings.get('JOBDIR'))
        crawler.signals.connect(obj.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(obj.spider_opened, signal=signals.spider_opened)
        return obj

    def spider_closed(self, spider):
        if self.jobdir:
            with open(self.statefn, 'wb') as f:
                pickle.dump(spider.state, f, protocol=2)

    def spider_opened(self, spider):
        if self.jobdir and os.path.exists(self.statefn):
            with open(self.statefn, 'rb') as f:
                spider.state = pickle.load(f)
        else:
            spider.state = {}

    @property
    def statefn(self):
        return os.path.join(self.jobdir, 'spider.state')
