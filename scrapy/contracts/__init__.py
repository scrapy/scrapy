import sys
import re
import itertools
from functools import wraps
from unittest import TestCase
import warnings

from scrapy.utils.spider import iterate_spider_output
from scrapy.exceptions import ScrapyDeprecationWarning


class ContractsManager(object):
    contracts = {}

    def __init__(self, contracts):
        for contract in contracts:
            self.contracts[contract.name] = contract

    def extract_contracts(self, method):
        batch = []
        for line in method.__doc__.split('\n'):
            line = line.strip()

            if line.startswith('@'):
                mobj = re.match(r'@(\w+)\s*(.*)', line)
                if mobj:
                    name, input_string = mobj.groups()
                    batch.append(self.contracts[name](method, input_string))
            elif not line:
                yield batch
                batch = []

        if batch:
            yield batch

    def from_method(self, method, results):
        for contracts in self.extract_contracts(method):
            requests = filter(None, (contract.create_request() for contract in contracts))
            for request in requests:
                for contract in contracts:
                    request = contract.adjust_request(request)

                # execute pre and post hooks in order
                for contract in reversed(contracts):
                    request = contract.add_pre_hook(request, results)
                for contract in contracts:
                    request = contract.add_post_hook(request, results)

                self._clean_req(request, method, results)
                yield request

    def _clean_req(self, request, method, results):
        """ stop the request from returning objects and records any errors """

        cb = request.callback

        @wraps(cb)
        def cb_wrapper(response):
            try:
                output = cb(response)
                output = list(iterate_spider_output(output))
            except:
                case = _create_testcase(method, 'callback')
                results.addError(case, sys.exc_info())

        def eb_wrapper(failure):
            case = _create_testcase(method, 'errback')
            exc_info = failure.value, failure.type, failure.getTracebackObject()
            results.addError(case, exc_info)

        request.callback = cb_wrapper
        request.errback = eb_wrapper


class Contract(object):
    """ Abstract class for contracts """

    def __init__(self, method, input_string):
        self.testcase_pre = _create_testcase(method, '@%s pre-hook' % self.name)
        self.testcase_post = _create_testcase(method, '@%s post-hook' % self.name)

        self.method = method
        self.input_string = input_string

    @property
    def args(self):
        warnings.warn("Contract.args attribute is deprecated and will be no longer supported, "
            "parse and use the raw Contract.input_string attribute instead", ScrapyDeprecationWarning, stacklevel=3)
        return re.split(r'\s+', self.input_string)

    def create_request(self):
        pass

    def adjust_request(self, request):
        return request

    def add_pre_hook(self, request, results):
        if hasattr(self, 'pre_process'):
            cb = request.callback

            @wraps(cb)
            def wrapper(response):
                try:
                    results.startTest(self.testcase_pre)
                    self.pre_process(response)
                    results.stopTest(self.testcase_pre)
                except AssertionError:
                    results.addFailure(self.testcase_pre, sys.exc_info())
                except Exception:
                    results.addError(self.testcase_pre, sys.exc_info())
                else:
                    results.addSuccess(self.testcase_pre)
                finally:
                    return list(iterate_spider_output(cb(response)))

            request.callback = wrapper

        return request

    def add_post_hook(self, request, results):
        if hasattr(self, 'post_process'):
            cb = request.callback

            @wraps(cb)
            def wrapper(response):
                output = list(iterate_spider_output(cb(response)))
                try:
                    results.startTest(self.testcase_post)
                    self.post_process(output)
                    results.stopTest(self.testcase_post)
                except AssertionError:
                    results.addFailure(self.testcase_post, sys.exc_info())
                except Exception:
                    results.addError(self.testcase_post, sys.exc_info())
                else:
                    results.addSuccess(self.testcase_post)
                finally:
                    return output

            request.callback = wrapper

        return request


def _create_testcase(method, desc):
    spider = method.__self__.name

    class ContractTestCase(TestCase):
        def __str__(_self):
            return "[%s] %s (%s)" % (spider, method.__name__, desc)

    name = '%s_%s' % (spider, method.__name__)
    setattr(ContractTestCase, name, lambda x: x)
    return ContractTestCase(name)
