"""
MemoryDebugger extension

See documentation in docs/topics/extensions.rst
"""

import gc
import logging
import six
import sys
import resource
from twisted.internet import task

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.trackref import live_refs, format_live_refs

logger = logging.getLogger(__name__)


class MemoryDebugger(object):

    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('MEMDEBUG_ENABLED'):
            raise NotConfigured
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        interval = spider.crawler.settings.getfloat('MEMDEBUG_LOG_INTERVAL', 30)
        self.task = task.LoopingCall(self.log_memory_usage, spider)
        self.task.start(interval)

    def spider_closed(self, spider, reason):
        gc.collect()
        self.stats.set_value('memdebug/gc_garbage_count', len(gc.garbage), spider=spider)
        for cls, wdict in six.iteritems(live_refs):
            if not wdict:
                continue
            self.stats.set_value('memdebug/live_refs/%s' % cls.__name__, len(wdict), spider=spider)
        if self.task.running:
            self.task.stop()

    def log_memory_usage(self, spider):
        memory_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != 'darwin':
            memory_usage *= 1024

        # print memory usage in kb for readability
        memory_usage /= 1024

        refs = format_live_refs()
        msg = "Memory usage: {!r} kb. Live References: \n {}\n"
        msg = msg.format(memory_usage, refs)
        logger.info(msg, extra={"spider": spider})
