"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""
from itertools import islice

from twisted.python.failure import Failure

from scrapy.exceptions import _InvalidOutput
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.python import MutableChain


def _isiterable(possible_iterator):
    return hasattr(possible_iterator, '__iter__')


def _fname(f):
    return "%s.%s".format(
        f.__self__.__class__.__name__,
        f.__func__.__name__
    )


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
            self.methods['process_start_requests'].appendleft(mw.process_start_requests)
        process_spider_output = getattr(mw, 'process_spider_output', None)
        self.methods['process_spider_output'].appendleft(process_spider_output)
        process_spider_exception = getattr(mw, 'process_spider_exception', None)
        self.methods['process_spider_exception'].appendleft(process_spider_exception)

    def scrape_response(self, scrape_func, response, request, spider):

        def process_spider_input(response):
            for method in self.methods['process_spider_input']:
                try:
                    result = method(response=response, spider=spider)
                    if result is not None:
                        msg = "Middleware {} must return None or raise an exception, got {}"
                        raise _InvalidOutput(msg.format(_fname(method), type(result)))
                except _InvalidOutput:
                    raise
                except Exception:
                    return scrape_func(Failure(), request, spider)
            return scrape_func(response, request, spider)

        def _evaluate_iterable(iterable, exception_processor_index, recover_to):
            try:
                for r in iterable:
                    yield r
            except Exception as ex:
                exception_result = process_spider_exception(Failure(ex), exception_processor_index)
                if isinstance(exception_result, Failure):
                    raise
                recover_to.extend(exception_result)

        def process_spider_exception(_failure, start_index=0):
            exception = _failure.value
            # don't handle _InvalidOutput exception
            if isinstance(exception, _InvalidOutput):
                return _failure
            method_list = islice(self.methods['process_spider_exception'], start_index, None)
            for method_index, method in enumerate(method_list, start=start_index):
                if method is None:
                    continue
                result = method(response=response, exception=exception, spider=spider)
                if _isiterable(result):
                    # stop exception handling by handing control over to the
                    # process_spider_output chain if an iterable has been returned
                    return process_spider_output(result, method_index + 1)
                elif result is None:
                    continue
                else:
                    msg = "Middleware {} must return None or an iterable, got {}"
                    raise _InvalidOutput(msg.format(_fname(method), type(result)))
            return _failure

        def process_spider_output(result, start_index=0):
            # items in this iterable do not need to go through the process_spider_output
            # chain, they went through it already from the process_spider_exception method
            recovered = MutableChain()

            method_list = islice(self.methods['process_spider_output'], start_index, None)
            for method_index, method in enumerate(method_list, start=start_index):
                if method is None:
                    continue
                try:
                    # might fail directly if the output value is not a generator
                    result = method(response=response, result=result, spider=spider)
                except Exception as ex:
                    exception_result = process_spider_exception(Failure(ex), method_index + 1)
                    if isinstance(exception_result, Failure):
                        raise
                    return exception_result
                if _isiterable(result):
                    result = _evaluate_iterable(result, method_index + 1, recovered)
                else:
                    msg = "Middleware {} must return an iterable, got {}"
                    raise _InvalidOutput(msg.format(_fname(method), type(result)))

            return MutableChain(result, recovered)

        def process_callback_output(result):
            recovered = MutableChain()
            result = _evaluate_iterable(result, 0, recovered)
            return MutableChain(process_spider_output(result), recovered)

        dfd = mustbe_deferred(process_spider_input, response)
        dfd.addCallbacks(callback=process_callback_output, errback=process_spider_exception)
        return dfd

    def process_start_requests(self, start_requests, spider):
        return self._process_chain('process_start_requests', start_requests, spider)
