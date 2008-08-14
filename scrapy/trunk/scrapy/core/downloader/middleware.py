"""
request-response middleware extension
"""
from scrapy.core import signals, log
from scrapy.http import Request, Response
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.misc import load_class, mustbe_deferred
from scrapy.core.downloader.handlers import download_any
from scrapy.conf import settings

class DownloaderMiddlewareManager(object):
    """Request-Response Middleware Manager

    Middleware is a framework of hooks into Scrapy's request/response
    processing.  It's a light, low-level "spider" system for globally altering
    Scrapy's input and/or output.

    Middleware is heavily based on Django middleware system, at the point that
    it tries to mimic Django middleware behaviour. For Scrapy, the Django's
    view function has the same meaning of the final download handler function
    to use for the request's url.

    To activate a middleware component, add it to the DOWNLOADER_MIDDLEWARES list
    in your Scrapy settings.  In DOWNLOADER_MIDDLEWARES, each middleware component
    is represented by a string: the full Python path to the middleware's class
    name. For example:

    DOWNLOADER_MIDDLEWARES = (
            'scrapy.contrib.middleware.common.SpiderMiddleware',
            'scrapy.contrib.middleware.common.CommonMiddleware',
            'scrapy.contrib.middleware.redirect.RedirectMiddleware',
            'scrapy.contrib.middleware.cache.CacheMiddleware',
    )

    Writing your own middleware is easy. Each middleware component is a single
    Python class that defines one or more of the following methods:


    process_request(self, request, spider)

        `request` is a Request object.
        `spider` is a BaseSpider object

        This method is called in each request until scrapy decides which
        download function to use.

        process_request() should return either None, Response or Request.

        If returns None, Scrapy will continue processing this request,
        executing any other middleware and, then, the appropiate download
        function.

        If returns a Response object, Scrapy won't bother calling ANY other
        request or exception middleware, or the appropiate download function;
        it'll return that Response. Response middleware is always called on
        every response.

        If returns a Request object, returned request is used to instruct a
        redirection. Redirection is handled inside middleware scope, and
        original request don't finish until redirected request is completed.


    process_response(self, request, response, spider):

        `request` is a Request object
        `response` is a Response object
        `spider` is a BaseSpider object

        process_response MUST return a Response object. It could alter the given
        response, or it could create a brand-new Response.


    process_exception(self, request, exception, spider)

        `request` is a Request object.
        `exception` is an Exception object
        `spider` is a BaseSpider object

        Scrapy calls process_exception() when a download handler or
        process_request middleware raises an exception.

        process_exception() should return either None, Response or Request object.

        if it returns None, Scrapy will continue processing this exception,
        executing any other exception middleware, until no middleware left and
        default exception handling kicks in.

        If it returns a Response object, the response middleware kicks in, and
        won't bother calling ANY other exception middleware.

        If it returns a Request object, returned request is used to instruct a
        immediate redirection. Redirection is handled inside middleware scope,
        and original request don't finish until redirected request is
        completed. This stop process_exception middleware as returning
        Response does.

    """
    def __init__(self):
        self.loaded = False
        self.request_middleware = []
        self.response_middleware = []
        self.exception_middleware = []
        self.load()
        self.download_function = download_any

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
        for mwpath in settings.getlist('DOWNLOADER_MIDDLEWARES') or ():
            cls = load_class(mwpath)
            if cls:
                try:
                    mw = cls()
                    self._add_middleware(mw)
                    mws.append(mw)
                except NotConfigured:
                    pass
        log.msg("Enabled downloader middlewares: %s" % ", ".join([type(m).__name__ for m in mws]))
        self.loaded = True

    def download(self, request, spider):
        def process_request(request):
            for method in self.request_middleware:
                response = method(request=request, spider=spider)
                assert response is None or isinstance(response, (Response, Request)), \
                        'Middleware %s.process_request must return None, Response or Request, got %s' % \
                        (method.im_self.__class__.__name__, response.__class__.__name__)
                if response:
                    return response
            return self.download_function(request=request, spider=spider)

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
