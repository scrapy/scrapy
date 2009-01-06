"""
Spider middleware manager
"""

from scrapy import log
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.misc import load_class
from scrapy.utils.defer import mustbe_deferred, defer_result
from scrapy.conf import settings

def _isiterable(possible_iterator):
    try:
        return iter(possible_iterator)
    except TypeError:
        return None

class SpiderMiddlewareManager(object):
    def __init__(self):
        self.loaded = False
        self.spider_middleware = []
        self.result_middleware = []
        self.exception_middleware = []
        self.load()

    def _add_middleware(self, mw):
        if hasattr(mw, 'process_scrape'):
            self.spider_middleware.append(mw.process_scrape)
        if hasattr(mw, 'process_result'):
            self.result_middleware.insert(0, mw.process_result)
        if hasattr(mw, 'process_exception'):
            self.exception_middleware.insert(0, mw.process_exception)

    def load(self):
        """Load middleware defined in settings module"""
        mws = []
        for mwpath in settings.getlist('SPIDER_MIDDLEWARES') or ():
            cls = load_class(mwpath)
            if cls:
                try:
                    mw = cls()
                    self._add_middleware(mw)
                    mws.append(mw)
                except NotConfigured:
                    pass
        log.msg("Enabled spider middlewares: %s" % ", ".join([type(m).__name__ for m in mws]))
        self.loaded = True

    def scrape(self, request, response, spider):
        fname = lambda f:'%s.%s' % (f.im_self.__class__.__name__, f.im_func.__name__)

        def process_scrape(response):
            for method in self.spider_middleware:
                result = method(response=response, spider=spider)
                assert result is None or _isiterable(result), \
                    'Middleware %s must returns None or an iterable object, got %s ' % \
                    (fname(method), type(result))
                if result is not None:
                    return result
            return self.call(request=request, response=response, spider=spider)


        def process_result(result):
            for method in self.result_middleware:
                result = method(response=response, result=result, spider=spider)
                assert _isiterable(result), \
                    'Middleware %s must returns an iterable object, got %s ' % \
                    (fname(method), type(result))
            return result

        def process_exception(_failure):
            exception = _failure.value
            for method in self.exception_middleware:
                result = method(response=response, exception=exception, spider=spider)
                assert result is None or _isiterable(result), \
                    'Middleware %s must returns None, or an iterable object, got %s ' % \
                    (fname(method), type(result))
                if result is not None:
                    return result
            return _failure

        dfd = mustbe_deferred(process_scrape, response)
        dfd.addErrback(process_exception)
        dfd.addCallback(process_result)
        return dfd

    def call(self, request, response, spider):
        defer_result(response).chainDeferred(request.deferred)
        return request.deferred
