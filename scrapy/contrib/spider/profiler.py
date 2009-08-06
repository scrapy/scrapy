"""
SpiderProfiler is an extension that hooks itself into every Request callback
returned from spiders to measure the processing time and memory allocation
caused by spiders code.

The results are collected using the StatsCollector.

This extension introduces a big impact on crawling performance, so enable only
for debugging.
"""

from time import time

from scrapy.xlib.pydispatch import dispatcher

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
            tbefore = time()
            mbefore = self._memusage()
            r = function(*args, **kwargs)
            mafter = self._memusage()
            ct = time() - tbefore
            domain = spider.domain_name
            tcc = stats.get_value('profiling/total_callback_time', 0, domain=domain)
            sct = stats.get_value('profiling/slowest_callback_time', 0, domain=domain)
            stats.set_value('profiling/total_callback_time' % spider.domain_name, tcc+ct, domain=domain)
            if ct > sct:
                stats.set_value('profiling/slowest_callback_time', ct, domain=domain)
                stats.set_value('profiling/slowest_callback_name', function.__name__, domain=domain)
                stats.set_value('profiling/slowest_callback_url', args[0].url, domain=domain)
            if self.memusage:
                tma = stats.get_value('profiling/total_mem_allocated_in_callbacks', 0, domain=domain)
                stats.set_value('profiling/total_mem_allocated_in_callbacks', tma+mafter-mbefore, domain=domain)
            return r
        return new_callback

    def _memusage(self):
        return self.memusage.virtual if self.memusage else 0.0
