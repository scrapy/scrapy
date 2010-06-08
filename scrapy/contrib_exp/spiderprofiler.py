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

from scrapy.core import signals
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.memory import get_vmvalue_from_procfs
from scrapy.stats import stats
from scrapy.conf import settings

class SpiderProfiler(object):
    
    def __init__(self):
        if not settings.getbool('SPIDERPROFILER_ENABLED'):
            raise NotConfigured
        try:
            get_vmvalue_from_procfs('VmSize')
        except RuntimeError:
            self._mem_tracking = False
        else:
            self._mem_tracking = True
        dispatcher.connect(self._request_received, signals.request_received)

    def _request_received(self, request, spider):
        request.callback = self._profiled_callback(request.callback, spider)

    def _profiled_callback(self, function, spider):
        def new_callback(*args, **kwargs):
            tbefore = time()
            mbefore = self._memusage()
            r = function(*args, **kwargs)
            mafter = self._memusage()
            ct = time() - tbefore
            tcc = stats.get_value('profiling/total_callback_time', 0, spider=spider)
            sct = stats.get_value('profiling/slowest_callback_time', 0, spider=spider)
            stats.set_value('profiling/total_callback_time', tcc+ct, spider=spider)
            if ct > sct:
                stats.set_value('profiling/slowest_callback_time', ct, spider=spider)
                stats.set_value('profiling/slowest_callback_name', function.__name__, \
                    spider=spider)
                stats.set_value('profiling/slowest_callback_url', args[0].url, \
                    spider=spider)
            if self._memusage:
                stats.inc_value('profiling/total_mem_allocated_in_callbacks', \
                    count=mafter-mbefore, spider=spider)
            return r
        return new_callback

    def _memusage(self):
        return get_vmvalue_from_procfs('VmSize') if self._mem_tracking else 0.0
