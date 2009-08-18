"""
This module implements the Scheduler Middleware manager.

For more information see the Scheduler Middleware doc in:
docs/topics/scheduler-middleware.rst

"""
from collections import defaultdict
from twisted.internet.defer import Deferred

from scrapy import log
from scrapy.http import Response
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list
from scrapy.conf import settings

class SchedulerMiddlewareManager(object):

    def __init__(self):
        self.loaded = False
        self.enabled = {}
        self.disabled = {}
        self.mw_cbs = defaultdict(list)
        self.load()

    def load(self):
        """Load middleware defined in settings module"""
        mwlist = build_component_list(settings['SCHEDULER_MIDDLEWARES_BASE'], \
            settings['SCHEDULER_MIDDLEWARES'])
        self.enabled.clear()
        self.disabled.clear()
        for mwpath in mwlist:
            try:
                cls = load_object(mwpath)
                mw = cls()
                self.enabled[cls.__name__] = mw
                self._add_middleware(mw)
            except NotConfigured, e:
                self.disabled[cls.__name__] = mwpath
                if e.args:
                    log.msg(e)
        log.msg("Enabled scheduler middlewares: %s" % ", ".join(self.enabled.keys()), \
            level=log.DEBUG)
        self.loaded = True

    def _add_middleware(self, mw):
        for name in ('enqueue_request', 'open_domain', 'close_domain'):
            mwfunc = getattr(mw, name, None)
            if mwfunc:
                self.mw_cbs[name].append(mwfunc)

    def enqueue_request(self, wrappedfunc, domain, request):
        def _enqueue_request(request):
            for mwfunc in self.mw_cbs['enqueue_request']:
                result = mwfunc(domain=domain, request=request)
                assert result is None or isinstance(result, (Response, Deferred)), \
                        'Middleware %s.enqueue_request must return None, Response or Deferred, got %s' % \
                        (mwfunc.im_self.__class__.__name__, result.__class__.__name__)
                if result:
                    return result
            return wrappedfunc(domain=domain, request=request)

        deferred = mustbe_deferred(_enqueue_request, request)
        return deferred

    def open_domain(self, domain):
        for mwfunc in self.mw_cbs['open_domain']:
            mwfunc(domain)

    def close_domain(self, domain):
        for mwfunc in self.mw_cbs['close_domain']:
            mwfunc(domain)
