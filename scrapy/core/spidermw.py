"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""
import six
from twisted.python.failure import Failure
from scrapy.exceptions import _InvalidOutput
from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list

def _isiterable(possible_iterator):
    return hasattr(possible_iterator, '__iter__')

class SpiderMiddlewareManager(MiddlewareManager):

    component_name = 'spider middleware'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('SPIDER_MIDDLEWARES'))

    def _add_middleware(self, mw):
        super(SpiderMiddlewareManager, self)._add_middleware(mw)
        if hasattr(mw, 'process_spider_input'):
            self.methods['process_spider_input'].append(mw.process_spider_input)
        if hasattr(mw, 'process_spider_output'):
            self.methods['process_spider_output'].insert(0, mw.process_spider_output)
        if hasattr(mw, 'process_spider_exception'):
            self.methods['process_spider_exception'].insert(0, mw.process_spider_exception)
        if hasattr(mw, 'process_start_requests'):
            self.methods['process_start_requests'].insert(0, mw.process_start_requests)

    def scrape_response(self, scrape_func, response, request, spider):
        fname = lambda f:'%s.%s' % (
                six.get_method_self(f).__class__.__name__,
                six.get_method_function(f).__name__)

        def process_spider_input(response):
            for method in self.methods['process_spider_input']:
                try:
                    result = method(response=response, spider=spider)
                    if result is not None:
                        raise _InvalidOutput('Middleware {} must return None or raise ' \
                            'an exception, got {}'.format(fname(method), type(result)))
                except:
                    return scrape_func(Failure(), request, spider)
            return scrape_func(response, request, spider)

        def process_spider_exception(_failure):
            exception = _failure.value
            # don't handle _InvalidOutput exception
            if isinstance(exception, _InvalidOutput):
                return _failure
            for method in self.methods['process_spider_exception']:
                result = method(response=response, exception=exception, spider=spider)
                if result is not None and not _isiterable(result):
                    raise _InvalidOutput('Middleware {} must return None or an iterable ' \
                        'object, got {}'.format(fname(method), type(result)))
                # stop exception handling by handing control over to the
                # process_spider_output chain if an iterable has been returned
                if result is not None:
                    return result
            return _failure

        def process_spider_output(result):
            def wrapper(result_iterable):
                try:
                    for r in result_iterable:
                        yield r
                except Exception as ex:
                    exception_result = process_spider_exception(Failure(ex))
                    if exception_result is None or isinstance(exception_result, Failure):
                        raise
                    for output in exception_result:
                        yield output
            for method in self.methods['process_spider_output']:
                result = method(response=response, result=result, spider=spider)
                if _isiterable(result):
                    result = wrapper(result)
                else:
                    raise _InvalidOutput('Middleware {} must return an iterable object, ' \
                        'got {}'.format(fname(method), type(result)))
            return result

        dfd = mustbe_deferred(process_spider_input, response)
        dfd.addErrback(process_spider_exception)
        dfd.addCallback(process_spider_output)
        return dfd

    def process_start_requests(self, start_requests, spider):
        return self._process_chain('process_start_requests', start_requests, spider)
