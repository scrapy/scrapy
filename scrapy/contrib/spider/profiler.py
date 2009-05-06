"""
SpiderProfiler is an extension that hooks itself into every Request callback
returned from spiders to measure the processing time and memory allocation
caused by spiders code.

The results are collected using the StatsCollector.

This extension introduces a big impact on crawling performance, so enable only
when needed.
"""

import datetime

from pydispatch import dispatcher

from scrapy.extension import extensions
from scrapy.core import signals
from scrapy.core.exceptions import NotConfigured
from scrapy.stats import stats
from scrapy.conf import settings

class SpiderProfiler(object):
    
    def __init__(self):
        if not settings.getbool('SPIDERPROFILER_ENABLED'):
            raise NotConfigured
        dispatcher.connect(self._request_received, signals.request_received)
        dispatcher.connect(self._engine_started, signals.engine_started)

    def _engine_started(self):
        self.memusage = extensions.enabled.get('MemoryUsage', None)

    def _request_received(self, request, spider):
        old_cbs = request.deferred.callbacks[0]
        new_cbs = ((self._profiled_callback(old_cbs[0][0], spider), old_cbs[0][1], old_cbs[0][2]), old_cbs[1])
        request.deferred.callbacks[0] = new_cbs

    def _profiled_callback(self, function, spider):
        def new_callback(*args, **kwargs):
            tbefore = datetime.datetime.now()
            mbefore = self._memusage()
            r = function(*args, **kwargs)
            tafter = datetime.datetime.now()
            mafter = self._memusage()
            ct = tafter-tbefore
            tcc = stats.getpath('%s/profiling/total_callback_time' % spider.domain_name, datetime.timedelta(0))
            sct = stats.getpath('%s/profiling/slowest_callback_time' % spider.domain_name, datetime.timedelta(0))
            stats.setpath('%s/profiling/total_callback_time' % spider.domain_name, tcc+ct)
            if ct > sct:
                stats.setpath('%s/profiling/slowest_callback_time' % spider.domain_name, ct)
                stats.setpath('%s/profiling/slowest_callback_name' % spider.domain_name, function.__name__)
                stats.setpath('%s/profiling/slowest_callback_url' % spider.domain_name, args[0].url)
            if self.memusage:
                tma = stats.getpath('%s/profiling/total_mem_allocated_in_callbacks' % spider.domain_name, 0)
                stats.setpath('%s/profiling/total_mem_allocated_in_callbacks' % spider.domain_name, tma+mafter-mbefore)
            return r
        return new_callback

    def _memusage(self):
        return self.memusage.virtual if self.memusage else 0.0
