from __future__ import annotations

import re
import sys
import warnings
from collections.abc import AsyncGenerator, Iterable
from functools import wraps
from inspect import getmembers, isasyncgenfunction, iscoroutinefunction
from types import CoroutineType
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import TestCase, TestResult

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.utils.asyncgen import collect_asyncgen
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_spec

if TYPE_CHECKING:
    from collections.abc import Callable

    from twisted.python.failure import Failure

    from scrapy import Spider


def _is_async(cb: Callable[..., Any]) -> bool:
    return iscoroutinefunction(cb) or isasyncgenfunction(cb)


def _collect(result: Any) -> list[Any]:
    if isinstance(result, (AsyncGenerator, CoroutineType)):
        if isinstance(result, CoroutineType):
            result.close()
        raise TypeError(
            "Callbacks that return a coroutine or an asynchronous generator "
            "must be defined with async def to be supported by contracts."
        )
    return list(arg_to_iter(result))


async def _collect_async(result: Any) -> list[Any]:
    if isinstance(result, AsyncGenerator):
        return await collect_asyncgen(result)
    if isinstance(result, CoroutineType):
        return await _collect_async(await result)
    return list(arg_to_iter(result))


def _run_hook(
    process: Callable[[Any], None],
    value: Any,
    testcase: TestCase,
    results: TestResult,
) -> None:
    try:
        results.startTest(testcase)
        process(value)
        results.stopTest(testcase)
    except AssertionError:
        results.addFailure(testcase, sys.exc_info())
    except Exception:
        results.addError(testcase, sys.exc_info())
    else:
        results.addSuccess(testcase)


class Contract:
    """Base class for :ref:`custom contracts <topics-contracts>`.

    *method* is the callback function to which the contract is associated.

    *args* is the list of arguments passed into the docstring, separated by
    whitespace.

    Subclasses may override :meth:`adjust_request_args`, and define a
    ``pre_process`` method or a ``post_process`` method, or both.
    """

    request_cls: type[Request] | None = None
    name: str

    def __init__(self, method: Callable[..., Any], *args: Any):
        self.testcase_pre = _create_testcase(method, f"@{self.name} pre-hook")
        self.testcase_post = _create_testcase(method, f"@{self.name} post-hook")
        self.args: tuple[Any, ...] = args

    def add_pre_hook(self, request: Request, results: TestResult) -> Request:
        if hasattr(self, "pre_process"):
            cb = request.callback
            assert cb is not None
            pre_process = self.pre_process
            testcase = self.testcase_pre

            if _is_async(cb):

                @wraps(cb)
                async def async_wrapper(
                    response: Response, **cb_kwargs: Any
                ) -> list[Any]:
                    _run_hook(pre_process, response, testcase, results)
                    return await _collect_async(cb(response, **cb_kwargs))

                request.callback = async_wrapper
            else:

                @wraps(cb)
                def wrapper(response: Response, **cb_kwargs: Any) -> list[Any]:
                    _run_hook(pre_process, response, testcase, results)
                    return _collect(cb(response, **cb_kwargs))

                request.callback = wrapper

        return request

    def add_post_hook(self, request: Request, results: TestResult) -> Request:
        if hasattr(self, "post_process"):
            cb = request.callback
            assert cb is not None
            post_process = self.post_process
            testcase = self.testcase_post

            if _is_async(cb):

                @wraps(cb)
                async def async_wrapper(
                    response: Response, **cb_kwargs: Any
                ) -> list[Any]:
                    output = await _collect_async(cb(response, **cb_kwargs))
                    _run_hook(post_process, output, testcase, results)
                    return output

                request.callback = async_wrapper
            else:

                @wraps(cb)
                def wrapper(response: Response, **cb_kwargs: Any) -> list[Any]:
                    output = _collect(cb(response, **cb_kwargs))
                    _run_hook(post_process, output, testcase, results)
                    return output

                request.callback = wrapper

        return request

    def adjust_request_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Receive a ``dict`` with the default arguments for the sample request
        and return it, either unmodified or with changes.

        :class:`~scrapy.Request` is used by default, but this can be changed
        with the ``request_cls`` attribute. If multiple contracts in the chain
        define this attribute, the last one is used.
        """
        return args


class ContractsManager:
    contracts: ClassVar[dict[str, type[Contract]]] = {}

    def __init__(self, contracts: Iterable[type[Contract]]):
        for contract in contracts:
            if (
                contract.add_pre_hook is not Contract.add_pre_hook
                or contract.add_post_hook is not Contract.add_post_hook
            ):
                warnings.warn(
                    f"{contract.__module__}.{contract.__qualname__} overrides"
                    " Contract.add_pre_hook() or Contract.add_post_hook(), which is"
                    " deprecated. Define pre_process() or post_process() instead."
                    " Contracts that override those methods do not support"
                    " asynchronous callbacks.",
                    ScrapyDeprecationWarning,
                    stacklevel=2,
                )
            self.contracts[contract.name] = contract

    def tested_methods_from_spidercls(self, spidercls: type[Spider]) -> list[str]:
        is_method = re.compile(r"^\s*@", re.MULTILINE).search
        methods = []
        for key, value in getmembers(spidercls):
            if callable(value) and value.__doc__ and is_method(value.__doc__):
                methods.append(key)

        return methods

    def extract_contracts(self, method: Callable[..., Any]) -> list[Contract]:
        contracts: list[Contract] = []
        assert method.__doc__ is not None
        for line_ in method.__doc__.split("\n"):
            line = line_.strip()

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
            bound_method = getattr(spider, method)
            try:
                requests.append(self.from_method(bound_method, results))
            except Exception:
                case = _create_testcase(bound_method, "contract")
                results.addError(case, sys.exc_info())

        return requests

    def from_method(
        self, method: Callable[..., Any], results: TestResult
    ) -> Request | None:
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
        self, request: Request, method: Callable[..., Any], results: TestResult
    ) -> None:
        """stop the request from returning objects and records any errors"""

        cb = request.callback
        assert cb is not None

        if _is_async(cb):

            @wraps(cb)
            async def cb_wrapper(response: Response, **cb_kwargs: Any) -> None:
                try:
                    await _collect_async(cb(response, **cb_kwargs))
                except Exception:
                    case = _create_testcase(method, "callback")
                    results.addError(case, sys.exc_info())

        else:

            @wraps(cb)
            def cb_wrapper(response: Response, **cb_kwargs: Any) -> None:
                try:
                    _collect(cb(response, **cb_kwargs))
                except Exception:
                    case = _create_testcase(method, "callback")
                    results.addError(case, sys.exc_info())

        def eb_wrapper(failure: Failure) -> None:
            case = _create_testcase(method, "errback")
            exc_info = failure.type, failure.value, failure.getTracebackObject()
            results.addError(case, exc_info)  # type: ignore[arg-type]

        request.callback = cb_wrapper
        request.errback = eb_wrapper


def _create_testcase(method: Callable[..., Any], desc: str) -> TestCase:
    spider = method.__self__.name  # type: ignore[attr-defined]

    class ContractTestCase(TestCase):
        def __str__(_self) -> str:  # pylint: disable=no-self-argument
            return f"[{spider}] {method.__name__} ({desc})"

    name = f"{spider}_{method.__name__}"
    setattr(ContractTestCase, name, lambda x: x)
    return ContractTestCase(name)
