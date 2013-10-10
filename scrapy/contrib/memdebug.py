"""
MemoryDebugger extension

See documentation in docs/topics/extensions.rst
"""

import gc

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.trackref import live_refs


class MemoryDebugger(object):

    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('MEMDEBUG_ENABLED'):
            raise NotConfigured
        o = cls(crawler.stats)
        crawler.signals.connect(o.engine_stopped, signals.engine_stopped)
        return o

    def engine_stopped(self):
        gc.collect()
        self.stats.set_value('memdebug/gc_garbage_count', len(gc.garbage))
        for cls, wdict in live_refs.iteritems():
            if not wdict:
                continue
            self.stats.set_value('memdebug/live_refs/%s' % cls.__name__, len(wdict))
