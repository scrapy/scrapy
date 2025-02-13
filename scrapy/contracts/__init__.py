from __future__ import annotations

import re
import sys
from collections.abc import AsyncGenerator, Callable, Iterable
from functools import wraps
from inspect import getmembers
from types import CoroutineType
from typing import Any, cast
from unittest import TestCase, TestResult

from scrapy.http import Request, Response
from scrapy.utils.python import get_spec
from scrapy.utils.spider import iterate_spider_output


def _wrap_callback(callback: Callable, test_method: Callable, testcase: TestCase, results: TestResult) -> Callable:
    @wraps(callback)
    def wrapper(response: Response, **cb_kwargs: Any) -> list[Any]:
        try:
            results.startTest(testcase)
            test_method(response)
            results.stopTest(testcase)
        except AssertionError:
            results.addFailure(testcase, sys.exc_info())
        except Exception:
            results.addError(testcase, sys.exc_info())
        else:
            results.addSuccess(testcase)
        return list(iterate_spider_output(callback(response, **cb_kwargs)))
    return wrapper


class Contract:
    request_cls: type[Request] | None = None
    name: str

    def __init__(self, method: Callable, *args: Any):
        self.testcase_pre = _create_testcase(method, f"@{self.name} pre-hook")
        self.testcase_post = _create_testcase(method, f"@{self.name} post-hook")
        self.args = args

    def add_pre_hook(self, request: Request, results: TestResult) -> Request:
        if hasattr(self, 'pre_process'):
            cb = request.callback
            assert cb is not None
            request.callback = _wrap_callback(cb, self.pre_process, self.testcase_pre, results)
        return request

    def add_post_hook(self, request: Request, results: TestResult) -> Request:
        if hasattr(self, 'post_process'):
            cb = request.callback
            assert cb is not None
            
            @wraps(cb)
            def wrapper(response: Response, **cb_kwargs: Any) -> list[Any]:
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
                return output
            
            request.callback = wrapper
        return request

    def adjust_request_args(self, args: dict[str, Any]) -> dict[str, Any]:
        return args


class ContractsManager:
    contracts: dict[str, type[Contract]] = {}

    def __init__(self, contracts: Iterable[type[Contract]]):
        self.contracts = {contract.name: contract for contract in contracts}

    def tested_methods_from_spidercls(self, spidercls: type) -> list[str]:
        return [key for key, value in getmembers(spidercls)
                if callable(value) and value.__doc__ 
                and re.compile(r"^\s*@", re.MULTILINE).search(value.__doc__)]

    def extract_contracts(self, method: Callable) -> list[Contract]:
        contracts = []
        for line in (method.__doc__ or '').split('\n'):
            if m := re.match(r"@(\w+)\s*(.*)", line.strip()):
                name, args = m.groups()
                if name in self.contracts:
                    contracts.append(self.contracts[name](method, *args.split()))
        return contracts

    def from_spider(self, spider: Any, results: TestResult) -> list[Request | None]:
        requests = []
        for method in self.tested_methods_from_spidercls(type(spider)):
            bound_method = getattr(spider, method)
            try:
                requests.append(self.from_method(bound_method, results))
            except Exception:
                results.addError(_create_testcase(bound_method, "contract"), sys.exc_info())
        return requests

    def from_method(self, method: Callable, results: TestResult) -> Request | None:
        contracts = self.extract_contracts(method)
        if not contracts:
            return None

        request_cls = next((c.request_cls for c in contracts if c.request_cls), Request)
        args, kwargs = get_spec(request_cls.__init__)
        kwargs.update({
            'dont_filter': True,
            'callback': method
        })

        for contract in contracts:
            kwargs = contract.adjust_request_args(kwargs)

        if not set(args) - {'self'} - set(kwargs):
            request = request_cls(**kwargs)
            for contract in reversed(contracts):
                request = contract.add_pre_hook(request, results)
            for contract in contracts:
                request = contract.add_post_hook(request, results)
            self._clean_req(request, method, results)
            return request
        return None

    def _clean_req(self, request: Request, method: Callable, results: TestResult) -> None:
        @wraps(request.callback)
        def cb_wrapper(response: Response, **cb_kwargs: Any) -> None:
            try:
                list(iterate_spider_output(request.callback(response, **cb_kwargs)))
            except Exception:
                results.addError(_create_testcase(method, "callback"), sys.exc_info())

        request.callback = cb_wrapper
        request.errback = lambda failure: results.addError(
            _create_testcase(method, "errback"),
            (failure.type, failure.value, failure.getTracebackObject())
        )


def _create_testcase(method: Callable, desc: str) -> TestCase:
    spider = method.__self__.name

    class ContractTestCase(TestCase):
        def __str__(_self) -> str:
            return f"[{spider}] {method.__name__} ({desc})"

    name = f"{spider}_{method.__name__}"
    setattr(ContractTestCase, name, lambda x: x)
    return ContractTestCase(name)
