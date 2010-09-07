"""
Scheduler Middleware manager

TODO: To be removed in Scrapy 0.11
"""

from twisted.internet.defer import Deferred

from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list

class SchedulerMiddlewareManager(MiddlewareManager):

    component_name = 'scheduler middleware'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings['DOWNLOADER_MIDDLEWARES_BASE'], \
            settings['DOWNLOADER_MIDDLEWARES'])

    def _add_middleware(self, mw):
        if hasattr(mw, 'enqueue_request'):
            self.methods['enqueue_request'].append(mw.enqueue_request)

    def enqueue_request(self, wrappedfunc, spider, request):
        def _enqueue_request(request):
            for mwfunc in self.methods['enqueue_request']:
                result = mwfunc(spider=spider, request=request)
                assert result is None or isinstance(result, Deferred), \
                        'Middleware %s.enqueue_request must return None or Deferred, got %s' % \
                        (mwfunc.im_self.__class__.__name__, result.__class__.__name__)
                if result:
                    return result
            return wrappedfunc(spider=spider, request=request)

        deferred = mustbe_deferred(_enqueue_request, request)
        return deferred
