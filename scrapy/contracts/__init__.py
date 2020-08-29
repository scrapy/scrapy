import sys
import re
from functools import wraps
from inspect import getmembers
from unittest import TestCase

from scrapy.http import Request
from scrapy.utils.spider import iterate_spider_output
from scrapy.utils.python import get_spec


class ContractsManager:
    contracts = {}

    def __init__(self, contracts):
        for contract in contracts:
            self.contracts[contract.name] = contract

    def tested_methods_from_spidercls(self, spidercls):
        is_method = re.compile(r"^\s*@", re.MULTILINE).search
        methods = []
        for key, value in getmembers(spidercls):
            if callable(value) and value.__doc__ and is_method(value.__doc__):
                methods.append(key)

        return methods

    def extract_contracts(self, method):
        contracts = []
        for line in method.__doc__.split('\n'):
            line = line.strip()

            if line.startswith('@'):
                name, args = re.match(r'@(\w+)\s*(.*)', line).groups()
                args = re.split(r'\s+', args)

                contracts.append(self.contracts[name](method, *args))

        return contracts

    def from_spider(self, spider, results):
        requests = []
        for method in self.tested_methods_from_spidercls(type(spider)):
            bound_method = spider.__getattribute__(method)
            try:
                requests.append(self.from_method(bound_method, results))
            except Exception:
                case = _create_testcase(bound_method, 'contract')
                results.addError(case, sys.exc_info())

        return requests

    def from_method(self, method, results):
        contracts = self.extract_contracts(method)
        if contracts:
            request_cls = Request
            for contract in contracts:
                if contract.request_cls is not None:
                    request_cls = contract.request_cls

            # calculate request args
            args, kwargs = get_spec(request_cls.__init__)

            # Don't filter requests to allow
            # testing different callbacks on the same URL.
            kwargs['dont_filter'] = True
            kwargs['callback'] = method

            for contract in contracts:
                kwargs = contract.adjust_request_args(kwargs)

            args.remove('self')

            # check if all positional arguments are defined in kwargs
            if set(args).issubset(set(kwargs)):
                request = request_cls(**kwargs)

                # execute pre and post hooks in order
                for contract in reversed(contracts):
                    request = contract.add_pre_hook(request, results)
                for contract in contracts:
                    request = contract.add_post_hook(request, results)

                self._clean_req(request, method, results)
                return request

    def _clean_req(self, request, method, results):
        """ stop the request from returning objects and records any errors """

        cb = request.callback

        @wraps(cb)
        def cb_wrapper(response, **cb_kwargs):
            try:
                output = cb(response, **cb_kwargs)
                output = list(iterate_spider_output(output))
            except Exception:
                case = _create_testcase(method, 'callback')
                results.addError(case, sys.exc_info())

        def eb_wrapper(failure):
            case = _create_testcase(method, 'errback')
            exc_info = failure.type, failure.value, failure.getTracebackObject()
            results.addError(case, exc_info)

        request.callback = cb_wrapper
        request.errback = eb_wrapper


class Contract:
    """ Abstract class for contracts """
    request_cls = None

    def __init__(self, method, *args):
        self.testcase_pre = _create_testcase(method, f'@{self.name} pre-hook')
        self.testcase_post = _create_testcase(method, f'@{self.name} post-hook')
        self.args = args

    def add_pre_hook(self, request, results):
        if hasattr(self, 'pre_process'):
            cb = request.callback

            @wraps(cb)
            def wrapper(response, **cb_kwargs):
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
                    return list(iterate_spider_output(cb(response, **cb_kwargs)))

            request.callback = wrapper

        return request

    def add_post_hook(self, request, results):
        if hasattr(self, 'post_process'):
            cb = request.callback

            @wraps(cb)
            def wrapper(response, **cb_kwargs):
                output = list(iterate_spider_output(cb(response, **cb_kwargs)))
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

    def adjust_request_args(self, args):
        return args


def _create_testcase(method, desc):
    spider = method.__self__.name

    class ContractTestCase(TestCase):
        def __str__(_self):
            return f"[{spider}] {method.__name__} ({desc})"

    name = f'{spider}_{method.__name__}'
    setattr(ContractTestCase, name, lambda x: x)
    return ContractTestCase(name)
