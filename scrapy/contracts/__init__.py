from __future__ import annotations

import re
import sys
from collections.abc import AsyncGenerator, Iterable
from functools import wraps
from inspect import getmembers
from types import CoroutineType
from typing import TYPE_CHECKING, Any, cast
from unittest import TestCase, TestResult

from scrapy.http import Request, Response
from scrapy.utils.python import get_spec
from scrapy.utils.spider import iterate_spider_output

if TYPE_CHECKING:
    from collections.abc import Callable

    from twisted.python.failure import Failure

    from scrapy import Spider


class Contract:
    """Abstract class for contracts"""

    request_cls: type[Request] | None = None
    name: str

    def __init__(self, method: Callable, *args: Any):
        self.testcase_pre = _create_testcase(method, f"@{self.name} pre-hook")
        self.testcase_post = _create_testcase(method, f"@{self.name} post-hook")
        self.args: tuple[Any, ...] = args

    def add_pre_hook(self, request: Request, results: TestResult) -> Request:
        if hasattr(self, "pre_process"):
            cb = request.callback
            assert cb is not None

            @wraps(cb)
            def wrapper(response: Response, **cb_kwargs: Any) -> list[Any]:
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
                cb_result = cb(response, **cb_kwargs)
                if isinstance(cb_result, (AsyncGenerator, CoroutineType)):
                    raise TypeError("Contracts don't support async callbacks")
                return list(cast(Iterable[Any], iterate_spider_output(cb_result)))

            request.callback = wrapper

        return request

    def add_post_hook(self, request: Request, results: TestResult) -> Request:
        if hasattr(self, "post_process"):
            cb = request.callback
            assert cb is not None

            @wraps(cb)
            def wrapper(response: Response, **cb_kwargs: Any) -> list[Any]:
                cb_result = cb(response, **cb_kwargs)
                if isinstance(cb_result, (AsyncGenerator, CoroutineType)):
                    raise TypeError("Contracts don't support async callbacks")
                output = list(cast(Iterable[Any], iterate_spider_output(cb_result)))
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
        for contract in contracts:
            self.contracts[contract.name] = contract

    def tested_methods_from_spidercls(self, spidercls: type[Spider]) -> list[str]:
        is_method = re.compile(r"^\s*@", re.MULTILINE).search
        methods = []
        for key, value in getmembers(spidercls):
            if callable(value) and value.__doc__ and is_method(value.__doc__):
                methods.append(key)

        return methods

    def extract_contracts(self, method: Callable) -> list[Contract]:
        contracts: list[Contract] = []
        assert method.__doc__ is not None
        for line in method.__doc__.split("\n"):
            line = line.strip()

            if line.startswith("@"):
                m = re.match(r"@(\w+)\s*(.*)", line)
                if m is None:
                    continue
                name, args = m.groups()
                args = re.split(r"\s+", args)

                contracts.append(self.contracts[name](method, *args))

        return contracts

    def from_spider(self, spider: Spider, results: TestResult) -> list[Request | None]:
        requests: list[Request | None] = []
        for method in self.tested_methods_from_spidercls(type(spider)):
            bound_method = spider.__getattribute__(method)
            try:
                requests.append(self.from_method(bound_method, results))
            except Exception:
                case = _create_testcase(bound_method, "contract")
                results.addError(case, sys.exc_info())

        return requests

    def from_method(self, method: Callable, results: TestResult) -> Request | None:
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
            kwargs["dont_filter"] = True
            kwargs["callback"] = method

            for contract in contracts:
                kwargs = contract.adjust_request_args(kwargs)

            args.remove("self")

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
        return None

    def _clean_req(
        self, request: Request, method: Callable, results: TestResult
    ) -> None:
        """stop the request from returning objects and records any errors"""

        cb = request.callback
        assert cb is not None

        @wraps(cb)
        def cb_wrapper(response: Response, **cb_kwargs: Any) -> None:
            try:
                output = cb(response, **cb_kwargs)
                output = list(cast(Iterable[Any], iterate_spider_output(output)))
            except Exception:
                case = _create_testcase(method, "callback")
                results.addError(case, sys.exc_info())

        def eb_wrapper(failure: Failure) -> None:
            case = _create_testcase(method, "errback")
            exc_info = failure.type, failure.value, failure.getTracebackObject()
            results.addError(case, exc_info)

        request.callback = cb_wrapper
        request.errback = eb_wrapper


def _create_testcase(method: Callable, desc: str) -> TestCase:
    spider = method.__self__.name  # type: ignore[attr-defined]

    class ContractTestCase(TestCase):
        def __str__(_self) -> str:  # pylint: disable=no-self-argument
            return f"[{spider}] {method.__name__} ({desc})"

    name = f"{spider}_{method.__name__}"
    setattr(ContractTestCase, name, lambda x: x)
    return ContractTestCase(name)
