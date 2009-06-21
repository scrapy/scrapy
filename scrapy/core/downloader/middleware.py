"""
This module implements the Downloader Middleware manager. For more information
see the Downloader Middleware doc in:

docs/topics/downloader-middleware.rst

"""

from scrapy.core import signals
from scrapy import log
from scrapy.http import Request, Response
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.middleware import build_middleware_list
from scrapy.conf import settings

class DownloaderMiddlewareManager(object):

    def __init__(self):
        self.loaded = False
        self.request_middleware = []
        self.response_middleware = []
        self.exception_middleware = []
        self.load()

    def _add_middleware(self, mw):
        if hasattr(mw, 'process_request'):
            self.request_middleware.append(mw.process_request)
        if hasattr(mw, 'process_response'):
            self.response_middleware.insert(0, mw.process_response)
        if hasattr(mw, 'process_exception'):
            self.exception_middleware.insert(0, mw.process_exception)

    def load(self):
        """Load middleware defined in settings module
        """
        mws = []
        mwlist = build_middleware_list(settings['DOWNLOADER_MIDDLEWARES_BASE'],
                                       settings['DOWNLOADER_MIDDLEWARES'])
        for mwpath in mwlist:
            cls = load_object(mwpath)
            if cls:
                try:
                    mw = cls()
                    self._add_middleware(mw)
                    mws.append(mw)
                except NotConfigured:
                    pass
        log.msg("Enabled downloader middlewares: %s" % ", ".join([type(m).__name__ for m in mws]))
        self.loaded = True

    def download(self, download_func, request, spider):
        def process_request(request):
            for method in self.request_middleware:
                response = method(request=request, spider=spider)
                assert response is None or isinstance(response, (Response, Request)), \
                        'Middleware %s.process_request must return None, Response or Request, got %s' % \
                        (method.im_self.__class__.__name__, response.__class__.__name__)
                if response:
                    return response
            return download_func(request=request, spider=spider)

        def process_response(response):
            assert response is not None, 'Received None in process_response'
            if isinstance(response, Request):
                return response

            for method in self.response_middleware:
                response = method(request=request, response=response, spider=spider)
                assert isinstance(response, (Response, Request)), \
                    'Middleware %s.process_response must return Response or Request, got %s' % \
                    (method.im_self.__class__.__name__, type(response))
                if isinstance(response, Request):
                    signals.send_catch_log(signal=signals.response_received, sender=self.__class__, response=response, spider=spider)
                    return response
            signals.send_catch_log(signal=signals.response_received, sender=self.__class__, response=response, spider=spider)
            return response

        def process_exception(_failure):
            exception = _failure.value
            for method in self.exception_middleware:
                response = method(request=request, exception=exception, spider=spider)
                assert response is None or isinstance(response, (Response, Request)), \
                    'Middleware %s.process_exception must return None, Response or Request, got %s' % \
                    (method.im_self.__class__.__name__, type(response))
                if response:
                    return response
            return _failure

        deferred = mustbe_deferred(process_request, request)
        deferred.addErrback(process_exception)
        deferred.addCallback(process_response)
        return deferred
