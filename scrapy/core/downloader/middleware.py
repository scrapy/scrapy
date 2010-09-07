"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""

from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list

class DownloaderMiddlewareManager(MiddlewareManager):

    component_name = 'downloader middleware'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings['DOWNLOADER_MIDDLEWARES_BASE'], \
            settings['DOWNLOADER_MIDDLEWARES'])

    def _add_middleware(self, mw):
        if hasattr(mw, 'process_request'):
            self.methods['process_request'].append(mw.process_request)
        if hasattr(mw, 'process_response'):
            self.methods['process_response'].insert(0, mw.process_response)
        if hasattr(mw, 'process_exception'):
            self.methods['process_exception'].insert(0, mw.process_exception)

    def download(self, download_func, request, spider):
        def process_request(request):
            for method in self.methods['process_request']:
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

            for method in self.methods['process_response']:
                response = method(request=request, response=response, spider=spider)
                assert isinstance(response, (Response, Request)), \
                    'Middleware %s.process_response must return Response or Request, got %s' % \
                    (method.im_self.__class__.__name__, type(response))
                if isinstance(response, Request):
                    return response
            return response

        def process_exception(_failure):
            exception = _failure.value
            for method in self.methods['process_exception']:
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
