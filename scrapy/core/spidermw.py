"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""
from itertools import chain

import six
from twisted.python.failure import Failure
from scrapy.exceptions import _InvalidOutput
from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list


def _isiterable(possible_iterator):
    return hasattr(possible_iterator, '__iter__')


class MutableChain:
    """
    Thin wrapper around itertools.chain, allowing to add iterables "in-place"
    """
    def __init__(self, *args):
        self.data = chain(*args)

    def extend(self, *iterables):
        self.data = chain(self.data, *iterables)

    def __iter__(self):
        return self.data.__iter__()

    def __next__(self):  # py3
        return self.data.__next__()

    def next(self):  # py2
        return self.data.next()


class SpiderMiddlewareManager(MiddlewareManager):

    component_name = 'spider middleware'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('SPIDER_MIDDLEWARES'))

    def _add_middleware(self, mw):
        super(SpiderMiddlewareManager, self)._add_middleware(mw)
        if hasattr(mw, 'process_spider_input'):
            self.methods['process_spider_input'].append(mw.process_spider_input)
        if hasattr(mw, 'process_start_requests'):
            self.methods['process_start_requests'].insert(0, mw.process_start_requests)
        self.methods['process_spider_output'].insert(0, getattr(mw, 'process_spider_output', None))
        self.methods['process_spider_exception'].insert(0, getattr(mw, 'process_spider_exception', None))

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

        def process_spider_exception(_failure, index):
            exception = _failure.value
            # don't handle _InvalidOutput exception
            if isinstance(exception, _InvalidOutput):
                return _failure
            for method in self.methods['process_spider_exception'][index:]:
                if method is None:
                    continue
                result = method(response=response, exception=exception, spider=spider)
                index += 1
                if _isiterable(result):
                    # stop exception handling by handing control over to the
                    # process_spider_output chain if an iterable has been returned
                    return process_spider_output(result, index)
                elif result is None:
                    continue
                else:
                    raise _InvalidOutput('Middleware {} must return None or an iterable, got {}' \
                                         .format(fname(method), type(result)))
            return _failure

        def process_spider_output(result, index):
            # items in this iterable do not need to go through the process_spider_output
            # chain, they went through it already from the process_spider_exception method
            recovered = MutableChain()

            def evaluate_result(result_iterable, index):
                try:
                    for r in result_iterable:
                        yield r
                except Exception as ex:
                    exception_result = process_spider_exception(Failure(ex), index+1)
                    if exception_result is None or isinstance(exception_result, Failure):
                        raise
                    recovered.extend(exception_result)

            for method in self.methods['process_spider_output'][index:]:
                if method is None:
                    continue
                result = method(response=response, result=result, spider=spider)
                index += 1
                if _isiterable(result):
                    result = evaluate_result(result, index)
                else:
                    raise _InvalidOutput('Middleware {} must return an iterable, got {}' \
                                         .format(fname(method), type(result)))

            return chain(result, recovered)

        dfd = mustbe_deferred(process_spider_input, response)
        dfd.addErrback(process_spider_exception, index=0)
        dfd.addCallback(process_spider_output, index=0)
        return dfd

    def process_start_requests(self, start_requests, spider):
        return self._process_chain('process_start_requests', start_requests, spider)
