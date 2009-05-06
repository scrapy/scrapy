"""
This module implements the Scheduler Middleware manager.

For more information see the Scheduler Middleware doc in:
docs/topics/scheduler-middleware.rst

"""
from twisted.internet.defer import Deferred

from scrapy import log
from scrapy.http import Response
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy.utils.defer import mustbe_deferred
from scrapy.conf import settings

class SchedulerMiddlewareManager(object):

    def __init__(self, scheduler):
        self.loaded = False
        self.scheduler = scheduler
        self.mw_enqueue_request = []
        self.load()

    def _add_middleware(self, mw):
        if hasattr(mw, 'enqueue_request'):
            self.mw_enqueue_request.append(mw.enqueue_request)

    def load(self):
        """Load middleware defined in settings module"""
        mws = []
        for mwpath in settings.getlist('SCHEDULER_MIDDLEWARES') or ():
            cls = load_object(mwpath)
            if cls:
                try:
                    mw = cls()
                    self._add_middleware(mw)
                    mws.append(mw)
                except NotConfigured:
                    pass
        log.msg("Enabled scheduler middlewares: %s" % ", ".join([type(m).__name__ for m in mws]))
        self.loaded = True

    def enqueue_request(self, domain, request, priority):
        def _enqueue_request(request):
            for method in self.mw_enqueue_request:
                result = method(domain=domain, request=request, priority=priority)
                assert result is None or isinstance(result, (Response, Deferred)), \
                        'Middleware %s.enqueue_request must return None, Response or Deferred, got %s' % \
                        (method.im_self.__class__.__name__, result.__class__.__name__)
                if result:
                    return result
            return self.scheduler.enqueue_request(domain=domain, request=request, priority=priority)

        deferred = mustbe_deferred(_enqueue_request, request)
        return deferred
